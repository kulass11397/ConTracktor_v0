import os,sqlite3,subprocess,hashlib
from pathlib import Path
root=Path(__file__).parent/'locked_database_test_v176_final'
root.mkdir(exist_ok=True);app=root/'App';app.mkdir(exist_ok=True)
db=root/'contractor_tracker.db'
c=sqlite3.connect(db);c.execute('CREATE TABLE IF NOT EXISTS test(value TEXT)');c.commit()
c.execute('BEGIN EXCLUSIVE')
before=hashlib.sha256(db.read_bytes()).hexdigest()
env=os.environ.copy();env.update(CONTRACTOR_INSTALL_TEST_DIR=str(app),
    CONTRACTOR_INSTALL_TEST_DATA_DIR=str(root),CONTRACTOR_DB_PATH=str(db))
try:
 p=subprocess.run([str(Path(__file__).parent/'release/ConTracktor_v1_Update_1.7.6.exe'),
    '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/DIR='+str(app),'/LOG='+str(root/'setup.log')],
    env=env,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
 assert p.returncode!=0,'Installer should reject an open database'
 assert not (app/'app.py').exists(),'Application was replaced despite database lock'
 assert hashlib.sha256(db.read_bytes()).hexdigest()==before,'Database changed'
 print('Open database correctly blocked installation; app and database remained unchanged. Exit='+str(p.returncode))
finally:c.rollback();c.close()
