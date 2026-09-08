using System.Windows;
using System.Windows.Controls;
using WachauEtappe.Zentrale.Models;

namespace WachauEtappe.Zentrale;

public partial class CandidateManagementWindow : Window
{
    private CandidateRecord? selected;
    public CandidateManagementWindow(){InitializeComponent();Loaded+=(_,_)=>LoadCandidates();}
    private void LoadCandidates(){CandidateList.ItemsSource=App.Database.GetCandidates(SearchBox.Text);}
    private void SearchBox_TextChanged(object sender,TextChangedEventArgs e){if(IsLoaded)LoadCandidates();}
    private static void SelectCombo(ComboBox box,string value){foreach(var item in box.Items.OfType<ComboBoxItem>())if(string.Equals(item.Content?.ToString(),value,StringComparison.OrdinalIgnoreCase)){box.SelectedItem=item;return;}box.SelectedIndex=0;}
    private static string ComboValue(ComboBox box,string fallback)=>(box.SelectedItem as ComboBoxItem)?.Content?.ToString()??fallback;
    private void CandidateList_SelectionChanged(object sender,SelectionChangedEventArgs e)
    {
        selected=CandidateList.SelectedItem as CandidateRecord;if(selected is null)return;
        CandidateIdText.Text=$"ID: {selected.Id}";NameBox.Text=selected.Name;LocationBox.Text=selected.Location;FitScoreBox.Text=selected.FitScore.ToString();EmailBox.Text=selected.Email;PhoneBox.Text=selected.Phone;UrlBox.Text=selected.Url;NotesBox.Text=selected.Notes;SelectCombo(PriorityBox,selected.Priority);SelectCombo(StatusBox,selected.Status);LastContactText.Text=string.IsNullOrWhiteSpace(selected.LastContactUtc)?"Noch kein Kontakt protokolliert":$"Letzter Kontakt: {selected.LastContactUtc}";
    }
    private void Apply(){if(selected is null)return;selected.Name=NameBox.Text.Trim();selected.Location=LocationBox.Text.Trim();selected.Priority=ComboValue(PriorityBox,"normal");selected.Status=ComboValue(StatusBox,"research");selected.Email=EmailBox.Text.Trim();selected.Phone=PhoneBox.Text.Trim();selected.Url=UrlBox.Text.Trim();selected.Notes=NotesBox.Text.Trim();if(int.TryParse(FitScoreBox.Text,out var score))selected.FitScore=Math.Clamp(score,0,100);}
    private void Save_Click(object sender,RoutedEventArgs e){if(selected is null)return;Apply();App.Database.SaveCandidate(selected);StatusText.Text="✓ Kandidat gespeichert.";LoadCandidates();}
    private void Contacted_Click(object sender,RoutedEventArgs e){if(selected is null)return;Apply();App.Database.SaveCandidate(selected);App.Database.MarkCandidateContacted(selected.Id);selected.Status="contacted";selected.LastContactUtc=DateTime.UtcNow.ToString("O");StatusText.Text="✓ Kontakt protokolliert.";LoadCandidates();}
}
