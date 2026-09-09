using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;

public partial class HostManagementWindow : Window
{
    private const string ApiBase = "https://web-production-907d68.up.railway.app";
    private const string PartnerPortalUrl = "https://topdiveair-sketch.github.io/Direcktbuchungen/partner/";
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(20) };
    private static readonly byte[] CredentialEntropy = Encoding.UTF8.GetBytes("WachauEtappe.Zentrale.AdminCredential.v1");
    private static readonly string CredentialDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WachauEtappe");
    private static readonly string CredentialFile = Path.Combine(CredentialDirectory, "railway-admin.cred");
    private HostRecord? selected;

    public HostManagementWindow()
    {
        InitializeComponent();
        Loaded += (_,_) =>
        {
            LoadHosts();
            UpdateAdminCredentialStatus();
        };
    }

    private void LoadHosts(){ HostList.ItemsSource = App.Database.GetHosts(SearchBox.Text); }
    private void SearchBox_TextChanged(object sender, TextChangedEventArgs e){ if(IsLoaded) LoadHosts(); }

    private void HostList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        selected = HostList.SelectedItem as HostRecord; if(selected is null) return;
        HostIdText.Text = $"ID: {selected.Id} · Status: {selected.Status}";
        PartnerHostIdBox.Text = selected.Id;
        NameBox.Text=selected.Name; LocationBox.Text=selected.Location;
        EmailBox.Text=selected.Email; PhoneBox.Text=selected.Phone; UrlBox.Text=selected.DirectUrl; CapacityBox.Text=App.Database.GetHostCapacity(selected.Id).ToString();
        OneNightCheck.IsChecked=selected.OneNightVerified; CashCheck.IsChecked=selected.CashAtHostVerified; LuggageCheck.IsChecked=selected.LuggageVerified; AcceptingCheck.IsChecked=selected.AcceptingBookings;
        StatusText.Text = selected.Published ? "✓ Öffentlich freigegeben" : "Noch nicht öffentlich freigegeben";
        PartnerCodeBox.Text=""; PartnerStatusText.Text="Online-Partnerstatus noch nicht geprüft.";
    }

    private void ApplyForm(){ if(selected is null) return; selected.Name=NameBox.Text.Trim(); selected.Location=LocationBox.Text.Trim(); selected.Email=EmailBox.Text.Trim(); selected.Phone=PhoneBox.Text.Trim(); selected.DirectUrl=UrlBox.Text.Trim(); selected.OneNightVerified=OneNightCheck.IsChecked==true; selected.CashAtHostVerified=CashCheck.IsChecked==true; selected.LuggageVerified=LuggageCheck.IsChecked==true; selected.AcceptingBookings=AcceptingCheck.IsChecked==true; }
    private void SaveCapacity(){if(selected is null)return;_ = int.TryParse(CapacityBox.Text,out var units);App.Database.SetHostCapacity(selected.Id,Math.Max(1,units));}
    private void Save_Click(object sender, RoutedEventArgs e){ if(selected is null) return; ApplyForm(); App.Database.SaveHost(selected); SaveCapacity(); StatusText.Text="✓ Änderungen lokal gespeichert und protokolliert."; LoadHosts(); }

    private void Publish_Click(object sender, RoutedEventArgs e)
    {
        if(selected is null) return; ApplyForm();
        if(!selected.OneNightVerified || !selected.CashAtHostVerified || !selected.LuggageVerified){ MessageBox.Show("Freigabe nicht möglich. 1-Nacht-Aufenthalt, Barzahlung und Gepäcktransport müssen bestätigt sein.","WachauEtappe Pflichtprüfung",MessageBoxButton.OK,MessageBoxImage.Warning); return; }
        selected.Status="verified"; selected.Published=true; App.Database.SaveHost(selected); SaveCapacity(); StatusText.Text="✓ Gastgeber geprüft und öffentlich freigegeben."; LoadHosts();
    }

    private void Unpublish_Click(object sender, RoutedEventArgs e){ if(selected is null) return; ApplyForm(); selected.Published=false; App.Database.SaveHost(selected); SaveCapacity(); StatusText.Text="Gastgeber wurde gesperrt und ist nicht öffentlich freigegeben."; LoadHosts(); }

    private void GeneratePartnerCode_Click(object sender, RoutedEventArgs e)
    {
        PartnerCodeBox.Text = Convert.ToHexString(RandomNumberGenerator.GetBytes(8));
        PartnerStatusText.Text = "Neues Partner-Passwort erzeugt. Jetzt 'Online-Zugang erstellen / aktualisieren' klicken.";
    }

    private string? ReadStoredAdminPassword()
    {
        try
        {
            if(!File.Exists(CredentialFile)) return null;
            var encrypted=File.ReadAllBytes(CredentialFile);
            var plain=ProtectedData.Unprotect(encrypted,CredentialEntropy,DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(plain);
        }
        catch
        {
            return null;
        }
    }

    private void StoreAdminPassword(string password)
    {
        Directory.CreateDirectory(CredentialDirectory);
        var plain=Encoding.UTF8.GetBytes(password);
        var encrypted=ProtectedData.Protect(plain,CredentialEntropy,DataProtectionScope.CurrentUser);
        File.WriteAllBytes(CredentialFile,encrypted);
    }

    private void UpdateAdminCredentialStatus()
    {
        AdminPasswordStatusText.Text = ReadStoredAdminPassword() is { Length: > 0 }
            ? "✓ Admin-Zugang ist für diesen Windows-Benutzer verschlüsselt gespeichert."
            : "Admin-Zugang noch nicht eingerichtet. Bitte einmal Railway-ADMIN_PASSWORD eingeben und 'Speichern & testen' klicken.";
    }

    private string? RequireAdminPassword()
    {
        var stored=ReadStoredAdminPassword();
        if(!string.IsNullOrWhiteSpace(stored)) return stored;
        MessageBox.Show("Bitte zuerst unten unter 'Online-Verwaltung' das Railway-ADMIN_PASSWORD einmalig speichern und testen.","Online-Verwaltung einrichten",MessageBoxButton.OK,MessageBoxImage.Information);
        return null;
    }

    private async Task<(bool ok,string message)> TestAdminPasswordAsync(string password)
    {
        try
        {
            using var req=new HttpRequestMessage(HttpMethod.Get,$"{ApiBase}/api/partner/admin-status?hostId=__credential_test__");
            req.Headers.Add("X-Admin-Password",password);
            var resp=await Http.SendAsync(req);
            if(resp.IsSuccessStatusCode) return (true,"✓ Verbindung zur WachauEtappe-Online-Zentrale erfolgreich.");
            if(resp.StatusCode==HttpStatusCode.Unauthorized) return (false,"✗ Admin-Passwort stimmt nicht mit Railway überein.");
            return (false,$"✗ Online-Zentrale antwortet mit HTTP {(int)resp.StatusCode}.");
        }
        catch(Exception ex)
        {
            return (false,$"✗ Verbindung zur Online-Zentrale fehlgeschlagen: {ex.Message}");
        }
    }

    private async void SaveAdminPassword_Click(object sender, RoutedEventArgs e)
    {
        var password=AdminPasswordBox.Password;
        if(string.IsNullOrWhiteSpace(password)){MessageBox.Show("Bitte das Railway-ADMIN_PASSWORD eingeben.");return;}
        AdminPasswordStatusText.Text="Verbindung wird geprüft …";
        var result=await TestAdminPasswordAsync(password);
        if(!result.ok){AdminPasswordStatusText.Text=result.message;return;}
        try
        {
            StoreAdminPassword(password);
            AdminPasswordBox.Clear();
            AdminPasswordStatusText.Text=result.message+" Admin-Zugang wurde verschlüsselt gespeichert.";
        }
        catch(Exception ex){AdminPasswordStatusText.Text=$"✗ Zugang konnte lokal nicht sicher gespeichert werden: {ex.Message}";}
    }

    private void ClearAdminPassword_Click(object sender, RoutedEventArgs e)
    {
        try{if(File.Exists(CredentialFile))File.Delete(CredentialFile);}catch{}
        AdminPasswordBox.Clear();
        UpdateAdminCredentialStatus();
    }

    private bool ValidatePartnerInput(out int rooms)
    {
        rooms=1;
        if(selected is null){MessageBox.Show("Bitte zuerst einen Gastgeber auswählen.");return false;}
        ApplyForm();
        if(string.IsNullOrWhiteSpace(selected.Name) || string.IsNullOrWhiteSpace(selected.Location)){MessageBox.Show("Name und Ort müssen ausgefüllt sein.");return false;}
        if(string.IsNullOrWhiteSpace(selected.Email) || !selected.Email.Contains('@')){MessageBox.Show("Bitte eine gültige Kontakt-E-Mail für den Gastgeber eintragen.");return false;}
        if(PartnerCodeBox.Text.Trim().Length<8){MessageBox.Show("Bitte ein Partner-Passwort mit mindestens 8 Zeichen eingeben oder erzeugen.");return false;}
        _=int.TryParse(CapacityBox.Text,out rooms);rooms=Math.Max(1,rooms);
        return true;
    }

    private async void ProvisionPartner_Click(object sender, RoutedEventArgs e)
    {
        if(!ValidatePartnerInput(out var rooms) || selected is null)return;
        var adminPassword=RequireAdminPassword(); if(adminPassword is null)return;
        try
        {
            App.Database.SaveHost(selected); SaveCapacity();
            var partnerPassword=PartnerCodeBox.Text.Trim();
            var payload=new {hostId=selected.Id,name=selected.Name,location=selected.Location,email=selected.Email,password=partnerPassword,roomsTotal=rooms};
            using var req=new HttpRequestMessage(HttpMethod.Post,$"{ApiBase}/api/partner/provision");
            req.Headers.Add("X-Admin-Password",adminPassword);
            req.Content=new StringContent(JsonSerializer.Serialize(payload),Encoding.UTF8,"application/json");
            var resp=await Http.SendAsync(req);var body=await resp.Content.ReadAsStringAsync();
            if(resp.StatusCode==HttpStatusCode.Unauthorized){PartnerStatusText.Text="✗ Der gespeicherte Admin-Zugang ist nicht mehr gültig. Bitte unten unter Online-Verwaltung neu speichern und testen.";return;}
            if(!resp.IsSuccessStatusCode){PartnerStatusText.Text=$"✗ Online-Zugang konnte nicht gespeichert werden ({(int)resp.StatusCode}): {body}";return;}
            PartnerStatusText.Text=$"✓ Online-Zugang aktiv. Login: Betriebs-ID {selected.Id} + Partner-Passwort.";
        }
        catch(Exception ex){PartnerStatusText.Text=$"✗ Verbindung zur Online-Zentrale fehlgeschlagen: {ex.Message}";}
    }

    private async void DisablePartner_Click(object sender, RoutedEventArgs e)
    {
        if(selected is null){MessageBox.Show("Bitte zuerst einen Gastgeber auswählen.");return;}
        var adminPassword=RequireAdminPassword(); if(adminPassword is null)return;
        if(MessageBox.Show($"Online-Zugang für {selected.Name} wirklich sperren?", "Partnerzugang sperren", MessageBoxButton.YesNo, MessageBoxImage.Warning)!=MessageBoxResult.Yes)return;
        try
        {
            using var req=new HttpRequestMessage(HttpMethod.Post,$"{ApiBase}/api/partner/disable");
            req.Headers.Add("X-Admin-Password",adminPassword);
            req.Content=new StringContent(JsonSerializer.Serialize(new {hostId=selected.Id}),Encoding.UTF8,"application/json");
            var resp=await Http.SendAsync(req);var body=await resp.Content.ReadAsStringAsync();
            if(resp.StatusCode==HttpStatusCode.Unauthorized){PartnerStatusText.Text="✗ Gespeicherter Admin-Zugang ungültig. Bitte Online-Verwaltung neu einrichten.";return;}
            PartnerStatusText.Text=resp.IsSuccessStatusCode?"✓ Online-Zugang gesperrt. Bestehende Partner-Sitzungen wurden beendet.":$"✗ Sperren fehlgeschlagen ({(int)resp.StatusCode}): {body}";
        }
        catch(Exception ex){PartnerStatusText.Text=$"✗ Verbindung zur Online-Zentrale fehlgeschlagen: {ex.Message}";}
    }

    private async void CheckPartnerStatus_Click(object sender, RoutedEventArgs e)
    {
        if(selected is null){MessageBox.Show("Bitte zuerst einen Gastgeber auswählen.");return;}
        var adminPassword=RequireAdminPassword(); if(adminPassword is null)return;
        try
        {
            using var req=new HttpRequestMessage(HttpMethod.Get,$"{ApiBase}/api/partner/admin-status?hostId={Uri.EscapeDataString(selected.Id)}");
            req.Headers.Add("X-Admin-Password",adminPassword);
            var resp=await Http.SendAsync(req);var body=await resp.Content.ReadAsStringAsync();
            if(resp.StatusCode==HttpStatusCode.Unauthorized){PartnerStatusText.Text="✗ Gespeicherter Admin-Zugang ungültig. Bitte Online-Verwaltung neu einrichten.";return;}
            if(!resp.IsSuccessStatusCode){PartnerStatusText.Text=$"✗ Statusprüfung fehlgeschlagen ({(int)resp.StatusCode}): {body}";return;}
            using var doc=JsonDocument.Parse(body);var root=doc.RootElement;
            if(!root.GetProperty("exists").GetBoolean()){PartnerStatusText.Text="Noch kein Online-Partnerzugang für diesen Betrieb vorhanden.";return;}
            var active=root.GetProperty("active").GetBoolean();var updated=root.GetProperty("updatedAt").GetString()??"";var last=root.GetProperty("lastLoginAt").GetString()??"";
            PartnerStatusText.Text=$"{(active?"✓ Aktiv":"⛔ Gesperrt")} · zuletzt geändert: {updated}"+(string.IsNullOrWhiteSpace(last)?" · noch kein Login":$" · letzter Login: {last}");
        }
        catch(Exception ex){PartnerStatusText.Text=$"✗ Verbindung zur Online-Zentrale fehlgeschlagen: {ex.Message}";}
    }

    private void CopyPortalLink_Click(object sender, RoutedEventArgs e)
    {
        Clipboard.SetText(PartnerPortalUrl);
        PartnerStatusText.Text="✓ Partnerportal-Link in die Zwischenablage kopiert.";
    }
}
