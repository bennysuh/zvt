# -*- coding: utf-8 -*-
from zvdata.utils.utils import to_float
from zvt.api.api import get_dividend_financing, get_spo_detail
from zvt.domain import SpoDetail, DividendFinancing

from zvt.recorders.eastmoney.common import EastmoneyPageabeDataRecorder
from zvt.utils.pd_utils import df_is_not_null
from zvt.utils.time_utils import now_pd_timestamp


class SPODetailRecorder(EastmoneyPageabeDataRecorder):
    data_schema = SpoDetail

    url = 'https://emh5.eastmoney.com/api/FenHongRongZi/GetZengFaMingXiList'
    page_url = url
    path_fields = ['ZengFaMingXiList']

    def get_original_time_field(self):
        return 'ZengFaShiJian'

    def get_data_map(self):
        return {
            "spo_issues": ("ShiJiZengFa", to_float),
            "spo_price": ("ZengFaJiaGe", to_float),
            "spo_raising_fund": ("ShiJiMuJi", to_float)
        }

    def on_finish(self):
        last_year = str(now_pd_timestamp().year)
        codes = [item.code for item in self.entities]
        need_filleds = get_dividend_financing(provider=self.provider, codes=codes,
                                              return_type='domain',
                                              session=self.session,
                                              filters=[DividendFinancing.spo_raising_fund.is_(None)],
                                              end_timestamp=last_year)

        for item in need_filleds:
            df = get_spo_detail(provider=self.provider, entity_id=item.entity_id,
                                columns=[SpoDetail.timestamp, SpoDetail.spo_raising_fund],
                                start_timestamp=item.timestamp,
                                end_timestamp="{}-12-31".format(item.timestamp.year))
            if df_is_not_null(df):
                item.spo_raising_fund = df['spo_raising_fund'].sum()
                self.session.commit()
        super().on_finish()


if __name__ == '__main__':
    # init_process_log('spo_detail.log')

    recorder = SPODetailRecorder(codes=['000999'])
    recorder.run()
