import sys,uuid,copy,io,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ereseta_local import config,database as db
from ereseta_local.opd_database import save_opd,list_opd,get_opd
from ereseta_local.opd_pdf import opd_pdf_bytes
from pypdf import PdfReader
import pypdfium2 as pdfium
root=Path(__file__).resolve().parent
config.DB_FILE=str(root/(uuid.uuid4().hex+'.db'));db.init_db();db.init_db()
draft=dict(patient=dict(first_name='Sample',middle_name='',last_name='Patient',age=30,address='Sample address'),hospital_no='OPD-001',date='2026-10-14',page=dict(width=8.5,height=11),soap=dict(S='Patient history and concerns.',O='Examination findings.',A='Assessment.',P='Plan and follow-up.'),hospital=config.DEFAULT_HOSPITAL,template=config.DEFAULT_TEMPLATE)
def read(data):
 reader=PdfReader(io.BytesIO(data));reader.decrypt('');return reader
normal=opd_pdf_bytes(draft);reader=read(normal);assert len(reader.pages)==1,len(reader.pages)
assert float(reader.pages[0].mediabox.width)==612 and float(reader.pages[0].mediabox.height)==792
text=reader.pages[0].extract_text();assert text.count('OPD RECORD SHEET')==1 and 'Plan and follow-up.' in text
(root/'opd-normal.pdf').write_bytes(normal)
# Render to inspect table proportions and header.
doc=pdfium.PdfDocument(normal);p=doc[0];b=p.render(scale=1.25);b.to_pil().save(root/'opd-normal.png');b.close();p.close();doc.close()
for key in 'SOAP':
 long=copy.deepcopy(draft);long['soap'][key]='\n'.join(f'{key} note {i:04d}: Text with <symbols> & details.' for i in range(280))
 pdf=opd_pdf_bytes(long);r=read(pdf);assert len(r.pages)>1
 text='\n'.join(p.extract_text() for p in r.pages)
 for i in range(280):assert f'{key} note {i:04d}:' in text,(key,i)
 assert 'CONTINUED' in text
 assert all(float(p.mediabox.height)==792 for p in r.pages)
 if key=='P':(root/'opd-long.pdf').write_bytes(pdf)
small=copy.deepcopy(draft);small['page']=dict(width=5.5,height=8.5);assert len(read(opd_pdf_bytes(small)).pages)==1
pid=db.find_or_create_patient('Sample','','Patient',30,'Female','Old address','Single')
rid=save_opd(draft,normal);assert list_opd('OPD-001')[0]['id']==rid
assert get_opd(rid)['pdf']==normal
p=db.get_all_patients()[0];assert p['sex']=='Female' and p['civil_status']=='Single'
db.find_or_create_patient('Sample','','Patient',31,'Female','Changed','Married')
assert json.loads(get_opd(rid)['payload'])['patient']['age']==30
assert not db.get_history()
assert db.get_setting('opd_page')['width']==8.5
print('PASS: letter/custom paper, single normal table, all SOAP sections overflow without lost text, immutable PDF/snapshot storage, patient demographics preserved, prescriptions untouched')
