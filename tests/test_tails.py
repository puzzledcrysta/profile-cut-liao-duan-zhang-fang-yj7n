from concurrent.futures import ThreadPoolExecutor
import pytest
from app.errors import DataError
from app.modules.tails import service
from app.store import connection


@pytest.fixture
def tail(client):
    def add(tail_id='T-001', length=1530, home='00101'):
        return client.post('/api/tails', json={'tail': tail_id, 'length': length, 'home': home})
    return add


def batches(client):
    return {row['batch']: row for row in client.get('/api/tails').json()['batches']}


def claim(client, request, tail_id='T-001', batch='00101'):
    return client.post('/api/claims', json={'request': request, 'tail': tail_id, 'batch': batch})


def test_register_and_board(client, tail):
    assert tail().status_code == 200
    tail('T-002', 2000)
    tail('T-003', 800, '00202')
    view = client.get('/api/tails').json()
    assert [row['id'] for row in view['tails']] == ['T-001', 'T-002', 'T-003']
    assert all(row['state'] == '在库' for row in view['tails'])
    first, second = batches(client)['00101'], batches(client)['00202']
    assert (first['claimable'], first['pieces'], first['on_hand']) == (3530, 2, 3530)
    assert second['claimable'] == 800


def test_register_deduplicated(client, tail):
    assert tail().json()['deduplicated'] is False
    again = tail()
    assert again.status_code == 200 and again.json()['deduplicated'] is True
    assert len(client.get('/api/tails').json()['tails']) == 1
    conflict = tail(length=999)
    assert (conflict.status_code, conflict.json()['code']) == (409, 'TAIL_CONFLICT')


def test_reserve_protects_from_lend(client, tail):
    tail()
    reserved = client.post('/api/tails/T-001/reserve').json()
    assert (reserved['state'], reserved['holder']) == ('预占', '00101')
    blocked = client.post('/api/tails/T-001/lend', json={'borrower': '急单R-7'})
    assert (blocked.status_code, blocked.json()['code']) == (409, 'TAIL_STATE')
    assert batches(client)['00101']['reserved'] == 1530
    client.post('/api/tails/T-001/unreserve')
    lent = client.post('/api/tails/T-001/lend', json={'borrower': '急单R-7'}).json()
    assert (lent['state'], lent['holder']) == ('借出', '急单R-7')
    assert lent['loan'] == 1


def test_return_restores_exactly_once(client, tail):
    tail()
    loan = client.post('/api/tails/T-001/lend', json={'borrower': '急单R-7'}).json()['loan']
    assert batches(client)['00101']['lent'] == 1530
    assert batches(client)['00101']['claimable'] == 0
    first = client.post(f'/api/loans/{loan}/return').json()
    assert first['restored'] is True and first['loan']['returned']
    assert batches(client)['00101']['claimable'] == 1530
    again = client.post(f'/api/loans/{loan}/return').json()
    assert again['restored'] is False
    assert batches(client)['00101']['claimable'] == 1530
    assert [row['state'] for row in client.get('/api/tails').json()['tails']] == ['在库']


def test_stale_return_cannot_close_new_loan(client, tail):
    tail()
    old = client.post('/api/tails/T-001/lend', json={'borrower': '急单R-7'}).json()['loan']
    client.post(f'/api/loans/{old}/return')
    new = client.post('/api/tails/T-001/lend', json={'borrower': '急单R-9'}).json()['loan']
    stale = client.post(f'/api/loans/{old}/return').json()
    assert stale['restored'] is False
    row = client.get('/api/tails').json()['tails'][0]
    assert (row['state'], row['holder'], row['loan']) == ('借出', '急单R-9', new)
    assert client.post(f'/api/loans/{new}/return').json()['restored'] is True
    assert client.get('/api/tails').json()['tails'][0]['state'] == '在库'


def test_claim_retry_never_doubles(client, tail):
    tail()
    first = claim(client, 'L-1').json()
    assert first['deduplicated'] is False and first['claim']['length'] == 1530
    retry = claim(client, 'L-1').json()
    assert retry['deduplicated'] is True and retry['claim'] == first['claim']
    slot = batches(client)['00101']
    assert (slot['claimed'], slot['claimable']) == (1530, 0)
    conflict = claim(client, 'L-1', tail_id='T-404')
    assert (conflict.status_code, conflict.json()['code']) == (409, 'CLAIM_CONFLICT')
    taken = claim(client, 'L-2')
    assert (taken.status_code, taken.json()['code']) == (409, 'TAIL_STATE')


def test_claim_limited_to_home_batch(client, tail):
    tail()
    foreign = claim(client, 'L-1', batch='00202')
    assert (foreign.status_code, foreign.json()['code']) == (409, 'TAIL_FOREIGN')
    slot = batches(client)['00101']
    assert slot['claimable'] == 1530 and '00202' not in batches(client)


def test_concurrent_claims_single_winner(client, tail):
    tail()
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda i: _try_claim(f'L-{i}'), range(8)))
    assert outcomes.count('ok') == 1 and outcomes.count('TAIL_STATE') == 7
    slot = batches(client)['00101']
    assert (slot['claimed'], slot['claimable']) == (1530, 0)
    with connection() as db:
        assert db.execute('SELECT COUNT(*) FROM claims').fetchone()[0] == 1


def test_concurrent_retry_single_deduction(client, tail):
    tail()
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: _try_claim('L-1'), range(8)))
    assert outcomes.count('ok') == 8
    assert batches(client)['00101']['claimed'] == 1530
    with connection() as db:
        assert db.execute('SELECT COUNT(*) FROM claims').fetchone()[0] == 1


def _try_claim(request):
    try:
        service.claim(request, 'T-001', '00101')
        return 'ok'
    except DataError as error:
        return error.code


def test_ledger_conservation(client, tail):
    tail('T-001', 1530)
    tail('T-002', 2000)
    tail('T-003', 800)
    client.post('/api/tails/T-001/reserve')
    loan = client.post('/api/tails/T-002/lend', json={'borrower': '急单R-7'}).json()['loan']
    claim(client, 'L-1', 'T-003')
    client.post(f'/api/loans/{loan}/return')
    slot = batches(client)['00101']
    assert slot['claimable'] + slot['lent'] + slot['claimed'] == 1530 + 2000 + 800
    assert (slot['reserved'], slot['on_hand'], slot['claimed']) == (1530, 2000, 800)


def test_unknown_and_validation(client):
    assert client.post('/api/tails/T-404/reserve').status_code == 404
    assert client.post('/api/tails/T-404/lend', json={'borrower': '急单R-7'}).status_code == 404
    assert client.post('/api/loans/404/return').status_code == 404
    assert claim(client, 'L-1', 'T-404').status_code == 404
    assert client.post('/api/tails', json={'tail': 'T-1', 'length': 0, 'home': 'A'}).status_code == 422
    assert client.post('/api/tails/T-1/lend', json={'borrower': '  '}).status_code == 422
