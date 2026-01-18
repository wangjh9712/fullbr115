from fastapi import APIRouter, HTTPException
from app.services.subscription import subscription_service
from app.models.schemas import SubscriptionRequest, Subscription
from typing import List

router = APIRouter(prefix="/subscribe", tags=["Subscription"])

@router.get("/list", response_model=List[Subscription])
async def get_subscriptions():
    return subscription_service.get_list()

@router.post("/add")
async def add_subscription(req: SubscriptionRequest):
    result = await subscription_service.add_subscription(req)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"message": result["message"]}

@router.delete("/{sub_id}")
async def delete_subscription(sub_id: str):
    return subscription_service.delete_subscription(sub_id)