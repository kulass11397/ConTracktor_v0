import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from app import Database,WD_RELINK_REVIEW_20260917

SOURCE=Path('C:/Users/Kyle/Downloads/contractor_tracker_backup_20260917_154825.db')

@unittest.skipUnless(SOURCE.exists(),'Reviewed client backup is not present on this device')
class ReviewedWithdrawalRepairTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'client.db'
        source=sqlite3.connect(f'file:{SOURCE.as_posix()}?mode=ro&immutable=1',uri=True)
        dest=sqlite3.connect(self.path)
        try:source.backup(dest)
        finally:dest.close();source.close()

    def links(self,db,ref):
        return {r['system_reference']:r['amount_cents'] for r in db.all('SELECT r.system_reference,s.amount_cents FROM cash_allocation_sources s JOIN remittances r ON r.id=s.withdrawal_id JOIN cash_allocations a ON a.id=s.allocation_id WHERE a.reference=?',(ref,))}

    def test_review_repairs_21_links_tracks_cancelled_duplicates_and_is_once_only(self):
        digest=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        db=Database(self.path)
        self.assertEqual(db.wd_reference_repair_status[0],'applied')
        for ref,spec in WD_RELINK_REVIEW_20260917['allocations'].items():self.assertEqual(self.links(db,ref),spec['new'])
        self.assertEqual(self.links(db,'DP-20260907-0001'),{'WD-20260907-0001':3700000})
        self.assertEqual(self.links(db,'DP-20260907-0002'),{'WD-20260907-0001':3700000})
        cancelled=db.one("SELECT id FROM remittances WHERE system_reference='WD-20260907-0001'")['id']
        self.assertEqual(db.withdrawal_available(cancelled),0)
        audit=db.one("SELECT COUNT(*) n FROM audit_log WHERE action='REVIEWED_WD_LINK_REPAIRED'")['n']
        self.assertEqual(audit,21);db.close()
        again=Database(self.path)
        try:
            self.assertEqual(again.wd_reference_repair_status[0],'already_applied')
            self.assertIsNone(again.updated_wd_repair_backup)
            self.assertEqual(again.one("SELECT COUNT(*) n FROM audit_log WHERE action='REVIEWED_WD_LINK_REPAIRED'")['n'],audit)
        finally:again.close()
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),digest)

    def test_changed_reviewed_withdrawal_blocks_all_new_repair(self):
        raw=sqlite3.connect(self.path);raw.execute("UPDATE remittances SET amount_cents=6305000 WHERE system_reference='WD-20260904-0001'");raw.commit();raw.close()
        db=Database(self.path)
        try:
            self.assertEqual(db.wd_reference_repair_status[0],'blocked')
            self.assertFalse(db.one("SELECT 1 FROM app_metadata WHERE key='reviewed_wd_relink_20260917'"))
            for ref,spec in WD_RELINK_REVIEW_20260917['allocations'].items():self.assertEqual(self.links(db,ref),spec['old'])
        finally:db.close()

    def test_returned_dp_reuses_correct_source_without_overallocating_cash(self):
        db=Database(self.path)
        try:
            wid=db.one("SELECT id FROM remittances WHERE system_reference='WD-20260904-0001'")['id']
            self.assertEqual(db.withdrawal_available(wid),0)
            release=db.one("""SELECT SUM(s.amount_cents) n FROM cash_pool_return_sources s JOIN cash_allocation_transactions t ON t.id=s.transaction_id
                JOIN cash_allocations a ON a.id=t.allocation_id WHERE a.reference='DP-20260904-0001' AND s.withdrawal_id=? AND t.voided=0""",(wid,))['n']
            self.assertEqual(release,6305000)
            wd_ids=[r['id'] for r in db.all("SELECT id FROM remittances WHERE type='Withdrawal' AND voided=0 AND txn_date>='2026-08-24'")]
            self.assertEqual(sum(db.withdrawal_available(wid) for wid in wd_ids),0)
        finally:db.close()

if __name__=='__main__':unittest.main()
