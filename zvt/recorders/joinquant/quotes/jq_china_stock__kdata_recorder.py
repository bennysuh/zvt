# -*- coding: utf-8 -*-
import argparse
import io
from datetime import timedelta

import pandas as pd
import requests
from jqdatasdk import auth, get_price, logout

from zvdata.recorder import FixedCycleDataRecorder
from zvdata.structs import IntervalLevel
from zvt.api.common import generate_kdata_id, to_jq_entity_id, get_kdata_schema, to_jq_trading_level
from zvt.api.rules import is_in_trading
from zvt.api.technical import get_kdata
from zvt.domain import Stock
from zvt.settings import JQ_ACCOUNT, JQ_PASSWD, SAMPLE_STOCK_CODES
from zvt.utils.time_utils import to_time_str, now_time_str, to_pd_timestamp, now_pd_timestamp
from zvt.utils.utils import init_process_log, read_csv


class JQChinaStockKdataRecorder(FixedCycleDataRecorder):
    entity_provider = 'eastmoney'
    entity_schema = Stock

    provider = 'joinquant'

    def __init__(self, entity_type='stock', exchanges=['sh', 'sz'], entity_ids=None, codes=None, batch_size=10,
                 force_update=False, sleeping_time=5, default_size=2000, one_shot=False, fix_duplicate_way='add',
                 start_timestamp=None, end_timestamp=None, contain_unfinished_data=False,
                 level=IntervalLevel.LEVEL_1DAY, kdata_use_begin_time=False, close_hour=15, close_minute=0,
                 one_day_trading_minutes=4 * 60) -> None:
        self.data_schema = get_kdata_schema(entity_type=entity_type, level=level)
        self.jq_trading_level = to_jq_trading_level(level)

        super().__init__(entity_type, exchanges, entity_ids, codes, batch_size, force_update, sleeping_time,
                         default_size, one_shot, fix_duplicate_way, start_timestamp, end_timestamp,
                         contain_unfinished_data, level, kdata_use_begin_time, close_hour, close_minute,
                         one_day_trading_minutes)

        self.current_factors = {}
        for security_item in self.entities:
            kdata = get_kdata(entity_id=security_item.id, provider=self.provider,
                              level=self.level.value, order=self.data_schema.timestamp.desc(),
                              limit=1,
                              return_type='domain',
                              session=self.session)
            if kdata:
                self.current_factors[security_item.id] = kdata[0].factor
                self.logger.info('{} latest factor:{}'.format(security_item.id, kdata[0].factor))

        auth(JQ_ACCOUNT, JQ_PASSWD)

    def get_data_map(self):
        return {}

    def generate_domain_id(self, entity, original_data):
        return generate_kdata_id(entity_id=entity.id, timestamp=original_data['timestamp'], level=self.level)

    def on_finish_entity(self, entity):
        kdatas = get_kdata(provider=self.provider, entity_id=entity.id, level=self.level.value,
                           order=self.data_schema.timestamp.asc(),
                           return_type='domain',
                           session=self.session,
                           filters=[self.data_schema.hfq_close.is_(None),
                                    self.data_schema.timestamp >= to_pd_timestamp('2005-01-01')])
        if kdatas:
            start = kdatas[0].timestamp
            end = kdatas[-1].timestamp

            # get hfq from joinquant
            df = get_price(to_jq_entity_id(entity), start_date=to_time_str(start), end_date=now_time_str(),
                           frequency='daily',
                           fields=['factor', 'open', 'close', 'low', 'high'],
                           skip_paused=True, fq='post')
            if df is not None and not df.empty:
                # fill hfq data
                for kdata in kdatas:
                    time_str = to_time_str(kdata.timestamp)
                    if time_str in df.index:
                        kdata.hfq_open = df.loc[time_str, 'open']
                        kdata.hfq_close = df.loc[time_str, 'close']
                        kdata.hfq_high = df.loc[time_str, 'high']
                        kdata.hfq_low = df.loc[time_str, 'low']
                        kdata.factor = df.loc[time_str, 'factor']
                self.session.commit()

                latest_factor = df.factor[-1]
                # factor not change yet, no need to reset the qfq past
                if latest_factor == self.current_factors.get(entity.id):
                    sql = 'UPDATE {} SET qfq_close=hfq_close/{},qfq_high=hfq_high/{}, qfq_open= hfq_open/{}, qfq_low= hfq_low/{} where ' \
                          'entity_id=\'{}\' and level=\'{}\' and (qfq_close isnull or qfq_high isnull or qfq_low isnull or qfq_open isnull)'.format(
                        self.data_schema.__table__, latest_factor, latest_factor, latest_factor, latest_factor,
                        entity.id, self.level.value)
                else:
                    sql = 'UPDATE {} SET qfq_close=hfq_close/{},qfq_high=hfq_high/{}, qfq_open= hfq_open/{}, qfq_low= hfq_low/{} where ' \
                          'entity_id=\'{}\' and level=\'{}\''.format(self.data_schema.__table__, latest_factor,
                                                                     latest_factor, latest_factor, latest_factor,
                                                                     entity.id,
                                                                     self.level.value)
                self.logger.info(sql)
                self.session.execute(sql)
                self.session.commit()

            # use netease provider to get turnover_rate
            query_url = 'http://quotes.money.163.com/service/chddata.html?code={}{}&start={}&end={}&fields=PCHG;TURNOVER'

            if entity.exchange == 'sh':
                exchange_flag = 0
            else:
                exchange_flag = 1

            url = query_url.format(exchange_flag, entity.code, to_time_str(start), to_time_str(end))
            response = requests.get(url=url)

            df = read_csv(io.BytesIO(response.content), encoding='GB2312', na_values='None')
            df['日期'] = pd.to_datetime(df['日期'])
            df.set_index('日期', drop=True, inplace=True)

            if df is not None and not df.empty:
                # fill turnover_rate, pct_change
                for kdata in kdatas:
                    if kdata.timestamp in df.index:
                        kdata.turnover_rate = df.loc[kdata.timestamp, '换手率']
                        kdata.change_pct = df.loc[kdata.timestamp, '涨跌幅']
                self.session.commit()

    def on_finish(self):
        super().on_finish()
        logout()

    def record(self, entity, start, end, size, timestamps):
        if self.start_timestamp:
            start = max(self.start_timestamp, to_pd_timestamp(start))

        end = now_pd_timestamp() + timedelta(days=1)

        start_timestamp = to_time_str(start)
        end_timestamp = to_time_str(end)
        # 不复权
        df = get_price(to_jq_entity_id(entity), start_date=to_time_str(start_timestamp),
                       end_date=end_timestamp,
                       frequency=self.jq_trading_level,
                       fields=['open', 'close', 'low', 'high', 'volume', 'money'],
                       skip_paused=True, fq=None)
        df.index.name = 'timestamp'
        df.reset_index(inplace=True)
        df['name'] = entity.name
        df.rename(columns={'money': 'turnover'}, inplace=True)

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['provider'] = 'joinquant'
        df['level'] = self.level.value

        # remove the unfinished kdata
        if is_in_trading(entity_type='stock', exchange='sh', timestamp=df.iloc[-1, :]['timestamp']):
            df = df.iloc[:-1, :]

        return df.to_dict(orient='records')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--level', help='trading level', default='1d', choices=[item.value for item in IntervalLevel])
    parser.add_argument('--codes', help='codes', default=SAMPLE_STOCK_CODES, nargs='+')

    args = parser.parse_args()

    level = IntervalLevel(args.level)
    codes = args.codes

    init_process_log('jq_china_stock_{}_kdata.log'.format(args.level))
    JQChinaStockKdataRecorder(level=level, sleeping_time=0, codes=codes).run()
