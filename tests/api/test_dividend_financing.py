from ..context import init_context

init_context()

from zvt.api.api import get_spo_detail, get_rights_issue_detail, get_dividend_financing
from zvt.domain import SpoDetail, RightsIssueDetail, DividendFinancing
from zvdata.domain import get_db_session
from zvt.utils.time_utils import to_pd_timestamp

session = get_db_session(provider='eastmoney',
                         db_name='dividend_financing')  # type: sqlalchemy.orm.Session


# 增发详情
def test_000778_spo_detial():
    result = get_spo_detail(session=session, provider='eastmoney', return_type='domain',
                            codes=['000778'], end_timestamp='2018-09-30',
                            order=SpoDetail.timestamp.desc())
    assert len(result) == 4
    latest: SpoDetail = result[0]
    assert latest.timestamp == to_pd_timestamp('2017-04-01')
    assert latest.spo_issues == 347600000
    assert latest.spo_price == 5.15
    assert latest.spo_raising_fund == 1766000000


# 配股详情
def test_000778_rights_issue_detail():
    result = get_rights_issue_detail(session=session, provider='eastmoney', return_type='domain',
                                     codes=['000778'], end_timestamp='2018-09-30',
                                     order=RightsIssueDetail.timestamp.desc())
    assert len(result) == 2
    latest: RightsIssueDetail = result[0]
    assert latest.timestamp == to_pd_timestamp('2001-09-10')
    assert latest.rights_issues == 43570000
    assert latest.rights_raising_fund == 492300000
    assert latest.rights_issue_price == 11.3


# 分红融资
def test_000778_dividend_financing():
    result = get_dividend_financing(session=session, provider='eastmoney', return_type='domain',
                                    codes=['000778'], end_timestamp='2018-09-30',
                                    order=DividendFinancing.timestamp.desc())
    assert len(result) == 22
    latest: DividendFinancing = result[1]
    assert latest.timestamp == to_pd_timestamp('2017')
    assert latest.dividend_money == 598632026.4
    assert latest.spo_issues == 347572815.0
    assert latest.rights_issues == 0
    assert latest.ipo_issues == 0
