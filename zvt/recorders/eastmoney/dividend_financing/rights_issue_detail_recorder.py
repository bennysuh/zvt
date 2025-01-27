# -*- coding: utf-8 -*-
from zvdata.utils.utils import to_float
from zvt.api.api import get_dividend_financing, get_rights_issue_detail
from zvt.domain import RightsIssueDetail, DividendFinancing

from zvt.recorders.eastmoney.common import EastmoneyPageabeDataRecorder
from zvt.settings import SAMPLE_STOCK_CODES
from zvt.utils.pd_utils import df_is_not_null
from zvt.utils.time_utils import now_pd_timestamp


class RightsIssueDetailRecorder(EastmoneyPageabeDataRecorder):
    data_schema = RightsIssueDetail

    url = 'https://emh5.eastmoney.com/api/FenHongRongZi/GetPeiGuMingXiList'
    page_url = url
    path_fields = ['PeiGuMingXiList']

    def get_original_time_field(self):
        return 'PeiGuGongGaoRi'

    def get_data_map(self):
        return {
            "rights_issues": ("ShiJiPeiGu", to_float),
            "rights_issue_price": ("PeiGuJiaGe", to_float),
            "rights_raising_fund": ("ShiJiMuJi", to_float)
        }

    def on_finish(self):
        last_year = str(now_pd_timestamp().year)
        codes = [item.code for item in self.entities]
        need_filleds = get_dividend_financing(provider=self.provider, codes=codes,
                                              return_type='domain',
                                              session=self.session,
                                              filters=[DividendFinancing.rights_raising_fund.is_(None)],
                                              end_timestamp=last_year)

        for item in need_filleds:
            df = get_rights_issue_detail(provider=self.provider, entity_id=item.entity_id,
                                         columns=[RightsIssueDetail.timestamp,
                                                  RightsIssueDetail.rights_raising_fund],
                                         start_timestamp=item.timestamp,
                                         end_timestamp="{}-12-31".format(item.timestamp.year))
            if df_is_not_null(df):
                item.rights_raising_fund = df['rights_raising_fund'].sum()
                self.session.commit()

        super().on_finish()


if __name__ == '__main__':
    # init_process_log('rights_issue.log')

    recorder = RightsIssueDetailRecorder(codes=SAMPLE_STOCK_CODES)
    recorder.run()
