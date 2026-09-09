using System.Diagnostics;
using System.Globalization;
using System.Net;
using System.Text;
using System.Windows;

namespace WachauEtappe.Zentrale;

public partial class BillingWindow : Window
{
    public BillingWindow()
    {
        InitializeComponent();
        Loaded += (_,_) => { InitDates(); LoadSettings(); RefreshInvoices(); };
    }

    private void InitDates()
    {
        var first=new DateTime(DateTime.Today.Year,DateTime.Today.Month,1).AddMonths(-1);
        FromDate.SelectedDate=first;
        ToDate.SelectedDate=first.AddMonths(1).AddDays(-1);
    }

    private void LoadSettings()
    {
        var s=App.Database.GetBillingSettings();
        FeeBox.Text=s.GetValueOrDefault("booking_fee_net","9.00");
        VatBox.Text=s.GetValueOrDefault("vat_rate","20.00");
        DaysBox.Text=s.GetValueOrDefault("payment_days","14");
        SellerNameBox.Text=s.GetValueOrDefault("seller_name","WachauEtappe");
        SellerAddressBox.Text=s.GetValueOrDefault("seller_address","");
        VatIdBox.Text=s.GetValueOrDefault("seller_vat_id","");
        IbanBox.Text=s.GetValueOrDefault("seller_iban","");
    }

    private bool SaveSettings()
    {
        if(!double.TryParse(FeeBox.Text.Replace(',','.'),NumberStyles.Any,CultureInfo.InvariantCulture,out var fee) || fee<0){MessageBox.Show("Bitte eine gültige Buchungsgebühr eingeben.");return false;}
        if(!double.TryParse(VatBox.Text.Replace(',','.'),NumberStyles.Any,CultureInfo.InvariantCulture,out var vat) || vat<0 || vat>100){MessageBox.Show("Bitte einen gültigen USt-Satz eingeben.");return false;}
        if(!int.TryParse(DaysBox.Text,out var days) || days<1){MessageBox.Show("Bitte ein gültiges Zahlungsziel eingeben.");return false;}
        App.Database.SaveBillingSettings(fee,vat,days,SellerNameBox.Text,SellerAddressBox.Text,VatIdBox.Text,IbanBox.Text);
        return true;
    }

    private void SaveSettings_Click(object sender,RoutedEventArgs e)
    {
        if(SaveSettings()) StatusText.Text="✓ Abrechnungseinstellungen gespeichert.";
    }

    private void Generate_Click(object sender,RoutedEventArgs e)
    {
        if(FromDate.SelectedDate is null || ToDate.SelectedDate is null){MessageBox.Show("Bitte einen Abrechnungszeitraum wählen.");return;}
        if(ToDate.SelectedDate<FromDate.SelectedDate){MessageBox.Show("Das Bis-Datum muss nach dem Von-Datum liegen.");return;}
        if(!SaveSettings())return;
        var from=FromDate.SelectedDate.Value.ToString("yyyy-MM-dd");var to=ToDate.SelectedDate.Value.ToString("yyyy-MM-dd");
        var x=App.Database.GeneratePartnerInvoices(from,to);
        StatusText.Text=x.invoices==0?"Keine neuen bestätigten Buchungen für diesen Zeitraum. Bereits verrechnete Buchungen werden nicht doppelt berechnet.":$"✓ {x.invoices} Rechnung(en) für {x.bookings} Buchung(en) erzeugt · Gesamt brutto € {x.gross:0.00}.";
        RefreshInvoices();
    }

    private void Refresh_Click(object sender,RoutedEventArgs e)=>RefreshInvoices();
    private void RefreshInvoices()=>InvoiceGrid.ItemsSource=App.Database.GetPartnerInvoices();

    private string? SelectedInvoiceId()
    {
        if(InvoiceGrid.SelectedItem is not Dictionary<string,object?> row)return null;
        return Convert.ToString(row.GetValueOrDefault("Id"));
    }

    private void Paid_Click(object sender,RoutedEventArgs e)
    {
        var id=SelectedInvoiceId();if(string.IsNullOrWhiteSpace(id)){MessageBox.Show("Bitte zuerst eine Rechnung auswählen.");return;}
        App.Database.MarkPartnerInvoicePaid(id,true);StatusText.Text="✓ Rechnung als bezahlt markiert.";RefreshInvoices();
    }

    private void OpenInvoice_Click(object sender,RoutedEventArgs e)
    {
        var id=SelectedInvoiceId();if(string.IsNullOrWhiteSpace(id)){MessageBox.Show("Bitte zuerst eine Rechnung auswählen.");return;}
        var inv=App.Database.GetPartnerInvoice(id);if(inv is null)return;var items=App.Database.GetPartnerInvoiceItems(id);var s=App.Database.GetBillingSettings();
        string H(object? v)=>WebUtility.HtmlEncode(Convert.ToString(v)??"");
        var sb=new StringBuilder();
        sb.Append("<!doctype html><html lang='de'><head><meta charset='utf-8'><title>Rechnung ").Append(H(inv["InvoiceNo"])).Append("</title><style>body{font-family:Segoe UI,Arial,sans-serif;color:#18251f;margin:45px;max-width:850px}h1{color:#173d32}.top{display:flex;justify-content:space-between;gap:30px}.box{margin:22px 0;padding:16px;background:#f4f6f3;border-radius:10px}table{width:100%;border-collapse:collapse;margin-top:22px}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left}.num{text-align:right}.totals{margin-left:auto;width:330px}.muted{color:#66736d;font-size:13px}</style></head><body>");
        sb.Append("<div class='top'><div><h1>WachauEtappe</h1><strong>").Append(H(s.GetValueOrDefault("seller_name","WachauEtappe"))).Append("</strong><br>").Append(H(s.GetValueOrDefault("seller_address","")).Replace("\n","<br>")).Append("<br><span class='muted'>UID/Steuernr.: ").Append(H(s.GetValueOrDefault("seller_vat_id",""))).Append("</span></div>");
        sb.Append("<div><h2>Rechnung ").Append(H(inv["InvoiceNo"])).Append("</h2><div>Zeitraum: ").Append(H(inv["PeriodFrom"])).Append(" – ").Append(H(inv["PeriodTo"])).Append("</div><div>Fällig: ").Append(H(inv["DueDate"])).Append("</div></div></div>");
        sb.Append("<div class='box'><strong>Rechnung an</strong><br>").Append(H(inv["HostName"])).Append("<br>").Append(H(inv["HostLocation"])).Append("<br>").Append(H(inv["HostEmail"])).Append("</div>");
        sb.Append("<table><thead><tr><th>Leistung</th><th>Aufenthalt</th><th>Buchungsreferenz</th><th class='num'>Netto</th></tr></thead><tbody>");
        foreach(var item in items)sb.Append("<tr><td>WachauEtappe Vermittlungsgebühr</td><td>").Append(H(item["StayDate"])).Append("</td><td>").Append(H(item["Reference"])).Append("</td><td class='num'>€ ").Append(Convert.ToDouble(item["AmountNet"]).ToString("0.00")).Append("</td></tr>");
        sb.Append("</tbody></table><table class='totals'><tr><td>Netto</td><td class='num'>€ ").Append(Convert.ToDouble(inv["Net"]).ToString("0.00")).Append("</td></tr><tr><td>USt ").Append(Convert.ToDouble(inv["VatRate"]).ToString("0.##")).Append(" %</td><td class='num'>€ ").Append(Convert.ToDouble(inv["Vat"]).ToString("0.00")).Append("</td></tr><tr><th>Gesamt</th><th class='num'>€ ").Append(Convert.ToDouble(inv["Gross"]).ToString("0.00")).Append("</th></tr></table>");
        sb.Append("<p>Zahlung per Überweisung an IBAN: <strong>").Append(H(s.GetValueOrDefault("seller_iban",""))).Append("</strong></p><p class='muted'>Hinweis: Vor produktiver Verwendung bitte vollständige Rechnungsanschriften und steuerliche Pflichtangaben prüfen.</p></body></html>");
        var folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),"WachauEtappe","Rechnungen");Directory.CreateDirectory(folder);var path=Path.Combine(folder,$"{inv["InvoiceNo"]}.html");File.WriteAllText(path,sb.ToString(),Encoding.UTF8);Process.Start(new ProcessStartInfo(path){UseShellExecute=true});StatusText.Text=$"✓ Rechnung geöffnet und gespeichert: {path}";
    }
}
