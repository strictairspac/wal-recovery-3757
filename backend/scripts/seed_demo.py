import os
from sqlalchemy import select
from src.config.database import Base,engine,Session
from src.models.entities import User,LogSet,CrashCase
from src.utils.security import hash_password
RECORDS=[{'op':'begin','tx':'T1'},{'op':'write','tx':'T1','key':'sample_A','value':75},{'op':'commit','tx':'T1'},{'op':'checkpoint'},{'op':'begin','tx':'T2'},{'op':'write','tx':'T2','key':'sample_B','value':40},{'op':'begin','tx':'T3'},{'op':'write','tx':'T3','key':'sample_A','value':60},{'op':'commit','tx':'T3'},{'op':'write','tx':'T2','key':'sample_B','value':35},{'op':'commit','tx':'T2'}]
# 早班/晚班各两个采样时刻：迟到校正按原采样时段补录。
SAMPLE_TIMES={'sample_A':['2026-11-17T08:00:00','2026-11-17T12:00:00','2026-11-17T20:00:00'],
              'sample_B':['2026-11-17T08:00:00','2026-11-17T12:00:00','2026-11-17T20:00:00']}
LATE_RECORDS=RECORDS+[
    {'op':'begin','tx':'C1'},
    {'op':'correct','tx':'C1','key':'sample_A','value':78,'start':'2026-11-17T08:00:00','end':'2026-11-17T12:00:00'},
    {'op':'commit','tx':'C1'},
]
def seed():
    Base.metadata.create_all(engine)
    if os.getenv('SEED_DEMO','true').lower()!='true':return
    with Session() as db:
        for role in ('admin','operator','viewer'):
            email=role+'@haili.local'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,role=role,password_hash=hash_password('Recovery2026!')))
        logs=db.scalar(select(LogSet).where(LogSet.name=='海砾采样账本-晚班'))
        if logs is None:
            logs=LogSet(name='海砾采样账本-晚班',description='A初始100份、B初始50份，T1提交后检查点，T2未提交，T3已提交',
                        initial={'sample_A':100,'sample_B':50},records=RECORDS,sample_times=SAMPLE_TIMES);db.add(logs);db.flush()
        elif not logs.sample_times:
            # 旧库升级时只补齐缺失的采样时刻，不覆盖用户修改。
            logs.sample_times=SAMPLE_TIMES;db.flush()
        corrected=db.scalar(select(LogSet).where(LogSet.name=='海砾采样账本-晚班-校正'))
        if corrected is None:
            corrected=LogSet(name='海砾采样账本-晚班-校正',description='在晚班账本后追加迟到校正C1，补录08:00—12:00的A读数',
                             initial={'sample_A':100,'sample_B':50},records=LATE_RECORDS,sample_times=SAMPLE_TIMES,parent_log_set_id=logs.id)
            db.add(corrected);db.flush()
        for name,point,log_set in [('断电点10-撤销T2',10,logs),('完整提交点11',11,logs),('初始点0',0,logs),
                                   ('校正未提交点13',13,corrected),('校正后断电点14',14,corrected)]:
            if not db.scalar(select(CrashCase).where(CrashCase.name==name)):db.add(CrashCase(name=name,log_set_id=log_set.id,crash_after=point))
        db.commit()
if __name__=='__main__':seed()
