import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / 'sample_data'
DB = Path(os.getenv('WORKBENCH_DB', str(ROOT/'state/ledger.sqlite3')))
TITLE = '料段账房'
SLUG = 'profile-cut'
KEY = '锯切计划'
FIELDS = ('标准棒料毫米', '锯缝毫米', '回用下限毫米', '余料清单', '切件规格')
ROLE = '门窗加工车间备料员'
UNIT = '毫米'
RULE_VERSION = 'profile-cut-1.0'
SIGNATURE = '料段去向'
TABS = {'intake': '备料凭证', 'contract': '型材规格', 'quality': '异常计划', 'domain': '型材排料', 'tails': '料尾台账', 'reconcile': '领料核对', 'runs': '锯切批次', 'review': '班组复核'}
