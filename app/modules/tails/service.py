from datetime import datetime, timezone
from app.errors import DataError
from app.store import connection

CLAIMABLE = ('在库', '预占')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def clean(value, label):
    text = value.strip()
    if not text:
        raise DataError('REQUIRED', f'{label}不能为空')
    return text


def fetch_tail(db, tail):
    row = db.execute('SELECT * FROM tails WHERE id=?', (tail,)).fetchone()
    if row is None:
        raise DataError('TAIL_UNKNOWN', f'没有料尾 {tail}', 404)
    return row


def register(tail, length, home):
    # 退料登记：同一编号重复登记且内容一致时直接返回原记录，不新增台账。
    tail, home = clean(tail, '料尾编号'), clean(home, '原签批批次')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT * FROM tails WHERE id=?', (tail,)).fetchone()
        if existing is not None:
            if existing['length'] != length or existing['home'] != home:
                raise DataError('TAIL_CONFLICT', f'料尾 {tail} 已登记且内容不一致', 409)
            return {**dict(existing), 'deduplicated': True}
        record = {'id': tail, 'length': length, 'home': home, 'state': '在库',
                  'holder': None, 'loan': None, 'seq': 0, 'updated': stamp()}
        db.execute('INSERT INTO tails VALUES (?,?,?,?,?,?,?,?)',
                   (record['id'], length, home, '在库', None, None, 0, record['updated']))
        return {**record, 'deduplicated': False}


def reserve(tail):
    # 预占：把在库料尾留给原签批批次，预占期间不能借出。
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = fetch_tail(db, tail)
        done = db.execute("UPDATE tails SET state='预占', holder=home, seq=seq+1, updated=? "
                          "WHERE id=? AND state='在库'", (stamp(), tail)).rowcount
        if done != 1:
            raise DataError('TAIL_STATE', f'料尾 {tail} 当前为{row["state"]}，不能预占', 409)
        return dict(fetch_tail(db, tail))


def unreserve(tail):
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = fetch_tail(db, tail)
        done = db.execute("UPDATE tails SET state='在库', holder=NULL, seq=seq+1, updated=? "
                          "WHERE id=? AND state='预占'", (stamp(), tail)).rowcount
        if done != 1:
            raise DataError('TAIL_STATE', f'料尾 {tail} 当前为{row["state"]}，不在预占中', 409)
        return dict(fetch_tail(db, tail))


def lend(tail, borrower):
    # 借出：只有在库料尾可借；借出单号落回料尾，归还时按单恢复。
    borrower = clean(borrower, '急单号')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = fetch_tail(db, tail)
        lent = stamp()
        done = db.execute("UPDATE tails SET state='借出', holder=?, seq=seq+1, updated=? "
                          "WHERE id=? AND state='在库'", (borrower, lent, tail)).rowcount
        if done != 1:
            raise DataError('TAIL_STATE', f'料尾 {tail} 当前为{row["state"]}，须回到在库才能借出', 409)
        loan_id = db.execute('INSERT INTO loans (tail,borrower,lent) VALUES (?,?,?)',
                             (tail, borrower, lent)).lastrowid
        db.execute('UPDATE tails SET loan=? WHERE id=?', (loan_id, tail))
        return dict(fetch_tail(db, tail))


def give_back(loan_id):
    # 归还：按借出单恢复一次；重复归还只回报现状，不再恢复，也不会关掉新借出单。
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        loan = db.execute('SELECT * FROM loans WHERE id=?', (loan_id,)).fetchone()
        if loan is None:
            raise DataError('LOAN_UNKNOWN', f'没有借出单 {loan_id}', 404)
        if loan['returned'] is not None:
            return {'loan': dict(loan), 'restored': False}
        returned = stamp()
        done = db.execute("UPDATE tails SET state='在库', holder=NULL, loan=NULL, seq=seq+1, updated=? "
                          "WHERE id=? AND state='借出' AND loan=?", (returned, loan['tail'], loan_id)).rowcount
        if done != 1:
            raise DataError('LOAN_STATE', f'借出单 {loan_id} 与料尾状态不一致', 409)
        db.execute('UPDATE loans SET returned=? WHERE id=? AND returned IS NULL', (returned, loan_id))
        loan = db.execute('SELECT * FROM loans WHERE id=?', (loan_id,)).fetchone()
        return {'loan': dict(loan), 'restored': True}


def claim(request, tail, batch):
    # 领用：领料单号为幂等键，重试返回原扣减结果；状态守卫保证并发下只有一方扣减成功。
    request, tail, batch = clean(request, '领料单号'), clean(tail, '料尾编号'), clean(batch, '领用批次')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT * FROM claims WHERE request=?', (request,)).fetchone()
        if existing is not None:
            if existing['tail'] != tail or existing['batch'] != batch:
                raise DataError('CLAIM_CONFLICT', f'领料单号 {request} 已用于其他领用', 409)
            return {'claim': dict(existing), 'deduplicated': True}
        row = fetch_tail(db, tail)
        if row['home'] != batch:
            raise DataError('TAIL_FOREIGN', f'料尾 {tail} 归属批次 {row["home"]}，{batch} 不能领用', 409)
        created = stamp()
        done = db.execute("UPDATE tails SET state='已领用', holder=?, seq=seq+1, updated=? "
                          "WHERE id=? AND state IN ('在库','预占')", (batch, created, tail)).rowcount
        if done != 1:
            raise DataError('TAIL_STATE', f'料尾 {tail} 当前为{row["state"]}，不能领用', 409)
        db.execute('INSERT INTO claims VALUES (?,?,?,?,?)', (request, tail, batch, row['length'], created))
        claim_row = db.execute('SELECT * FROM claims WHERE request=?', (request,)).fetchone()
        return {'claim': dict(claim_row), 'deduplicated': False}


def board():
    # 工作台视图：逐截状态与借还去向，以及每个原签批批次还能领多少。
    with connection() as db:
        tails = [dict(row) for row in db.execute('SELECT * FROM tails ORDER BY id')]
        loans = [dict(row) for row in db.execute('SELECT * FROM loans ORDER BY id')]
    by_tail = {}
    for loan in loans:
        by_tail.setdefault(loan['tail'], []).append(loan)
    batches = {}
    for tail in tails:
        tail['loans'] = by_tail.get(tail['id'], [])
        slot = batches.setdefault(tail['home'], {'batch': tail['home'], 'claimable': 0, 'pieces': 0,
                                                 'reserved': 0, 'on_hand': 0, 'lent': 0, 'claimed': 0})
        if tail['state'] in CLAIMABLE:
            slot['claimable'] += tail['length']
            slot['pieces'] += 1
            slot['reserved' if tail['state'] == '预占' else 'on_hand'] += tail['length']
        elif tail['state'] == '借出':
            slot['lent'] += tail['length']
        else:
            slot['claimed'] += tail['length']
    return {'tails': tails, 'batches': sorted(batches.values(), key=lambda slot: slot['batch'])}
