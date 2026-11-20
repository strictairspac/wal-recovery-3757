from typing import Literal,Union
from pydantic import BaseModel, Field
class WalRecord(BaseModel):
    op: Literal['begin','write','commit','abort','checkpoint','correct']
    tx: str | None = Field(default=None,max_length=30,pattern=r'^[A-Za-z0-9_-]+$')
    key: str | None = Field(default=None,max_length=50,pattern=r'^[A-Za-z0-9_-]+$')
    value: int | None = Field(default=None,ge=-1000000000,le=1000000000)
    at: str | None = Field(default=None,max_length=40,description='write的采样时刻（可选）')
    start: str | None = Field(default=None,max_length=40,description='correct时段的起点（含）')
    end: str | None = Field(default=None,max_length=40,description='correct时段的终点（不含）')
class LogSetInput(BaseModel):
    name: str=Field(min_length=2,max_length=100)
    initial: dict[str,int]=Field(min_length=1,max_length=30)
    records: list[WalRecord]=Field(min_length=1,max_length=200)
    sample_times: dict[str,Union[str,list[str]]]=Field(default_factory=dict,description='键到采样时刻的映射')
    description: str=Field(default='',max_length=500)
class CorrectionItem(BaseModel):
    key: str=Field(min_length=1,max_length=50,pattern=r'^[A-Za-z0-9_-]+$')
    value: int=Field(ge=-1000000000,le=1000000000)
    start: str=Field(min_length=1,max_length=40)
    end: str=Field(min_length=1,max_length=40)
class CorrectionInput(BaseModel):
    name: str=Field(min_length=2,max_length=100,description='派生日志集名称')
    description: str=Field(default='',max_length=500)
    tx: str=Field(min_length=1,max_length=30,pattern=r'^[A-Za-z0-9_-]+$')
    corrections: list[CorrectionItem]=Field(min_length=1,max_length=50)
    commit: bool=True
