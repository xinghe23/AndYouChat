from fastapi import APIRouter

from app.api.v1 import auth, conversations, friends, messages, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(friends.router)
api_router.include_router(conversations.router)
api_router.include_router(messages.router)
