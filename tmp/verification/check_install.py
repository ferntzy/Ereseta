from contextlib import closing
import importlib.util, json, sqlite3, tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('installer','tools/install_local.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(dir='tmp') as temp:
 root=Path(temp).resolve();src=root/'source';dst=root/'installed';src.mkdir();(src/'assets').mkdir();(src/'prescriptions').mkdir()
 (src/'EReseta.exe').write_bytes(b'test');asset=src/'assets'/'sig.png';asset.write_bytes(b'signature');pdf=src/'prescriptions'/'saved.pdf';pdf.write_bytes(b'pdf')
 with closing(sqlite3.connect(src/'ereseta_local.db')) as db, db:
  db.executescript('CREATE TABLE physicians(id INTEGER,signature_path TEXT); CREATE TABLE prescriptions(id INTEGER,pdf_path TEXT); CREATE TABLE settings(key TEXT,value TEXT);')
  db.execute('INSERT INTO physicians VALUES(1,?)',(str(asset),));db.execute('INSERT INTO prescriptions VALUES(1,?)',(str(pdf),));db.execute('INSERT INTO settings VALUES(?,?)',('template',json.dumps({'signature_img':{'path':str(asset)}})))
 module.install(src,dst)
 with closing(sqlite3.connect(dst/'ereseta_local.db')) as db, db:
  assert Path(db.execute('SELECT signature_path FROM physicians').fetchone()[0])==dst/'assets'/'sig.png'
  assert Path(db.execute('SELECT pdf_path FROM prescriptions').fetchone()[0]).is_file()
  db.execute('INSERT INTO physicians VALUES(2,NULL)')
 module.install(src,dst)
 with closing(sqlite3.connect(dst/'ereseta_local.db')) as db:assert db.execute('SELECT count(*) FROM physicians').fetchone()[0]==2
 print('PASS: migration relocates assets/PDFs and repeated installs preserve installed data')
