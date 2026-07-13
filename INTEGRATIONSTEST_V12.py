from pathlib import Path
import os, sys, tempfile

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
os.environ['ADMIN_PASSWORD']='test-password-123'
import app

client=app.app.test_client()
results=[]
def test(name, response, allowed=(200,)):
    ok=response.status_code in allowed
    results.append((name,ok,response.status_code))

# public
test('Startseite',client.get('/'))
test('Admin-Login-Seite',client.get('/admin/login'))
test('Health',client.get('/health'))

with client:
    r=client.post('/admin/login',data={'password':'test-password-123'},follow_redirects=False)
    test('Admin Login',r,(302,))
    for path in ['/smart','/assistent','/heute','/os','/wissen','/admin','/setup','/quality','/quality/report.json']:
        test(path,client.get(path))
    # setup update
    test('Setup speichern',client.post('/setup',data={'key':'rooms','completed':'on','note':'Test'},follow_redirects=True))
    # create staff user
    test('Benutzer anlegen',client.post('/quality/user',data={'username':'tester','display_name':'Test','password':'abcdefgh','role':'staff'},follow_redirects=True))
    # restore point
    test('Restore Point',client.post('/quality/restore-point',follow_redirects=True))
    # sample CSV
    test('CSV Vorlage',client.get('/quality/import/sample.csv'))

with client:
    test('Staff Login',client.post('/staff/login',data={'username':'tester','password':'abcdefgh'},follow_redirects=False),(302,))

passed=sum(1 for _,ok,_ in results if ok)
print(f'{passed}/{len(results)} erfolgreich')
for name,ok,status in results:
    print(('OK' if ok else 'FEHLER'),name,status)
if passed != len(results):
    raise SystemExit(1)
