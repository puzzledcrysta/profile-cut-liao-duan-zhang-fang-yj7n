from fastapi import APIRouter
from app.inputs import ClaimIn, LendIn, TailIn
from . import service

router = APIRouter()


@router.get('/api/tails')
def board():
    return service.board()


@router.post('/api/tails')
def register(payload: TailIn):
    return service.register(payload.tail, payload.length, payload.home)


@router.post('/api/tails/{tail}/reserve')
def reserve(tail: str):
    return service.reserve(tail)


@router.post('/api/tails/{tail}/unreserve')
def unreserve(tail: str):
    return service.unreserve(tail)


@router.post('/api/tails/{tail}/lend')
def lend(tail: str, payload: LendIn):
    return service.lend(tail, payload.borrower)


@router.post('/api/loans/{loan_id}/return')
def give_back(loan_id: int):
    return service.give_back(loan_id)


@router.post('/api/claims')
def claim(payload: ClaimIn):
    return service.claim(payload.request, payload.tail, payload.batch)
