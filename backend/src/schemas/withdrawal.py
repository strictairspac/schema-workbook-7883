from pydantic import BaseModel,Field
class WithdrawalInput(BaseModel):
    relation_id:int=Field(gt=0)
    field:str=Field(min_length=1,max_length=40)
