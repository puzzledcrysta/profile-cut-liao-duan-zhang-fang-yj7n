from decimal import Decimal as D
from app.errors import DataError
from .values import whole, parts


def batches(text):
    values = []
    for item in parts(text):
        size, sep, count = item.partition('x')
        if not sep:
            raise DataError('CUT_FORMAT', '规格格式为长度x件数')
        values.append((whole(size, 1, 100000), whole(count, 1, 200)))
    if sum(count for _, count in values) > 500:
        raise DataError('CUT_LIMIT', '单计划至多 500 段')
    return values


def evaluate(row):
    stock = whole(row['标准棒料毫米'], 1, 100000)
    kerf = whole(row['锯缝毫米'], 0, 30)
    reuse = whole(row['回用下限毫米'], 1, stock)
    pieces = sorted((size for size, count in batches(row['切件规格']) for _ in range(count)), reverse=True)
    if not pieces or pieces[0] > stock:
        raise DataError('CUT_SIZE', '切件为空或长于标准棒料')
    pool = [size for size,count in batches(row['余料清单']) for _ in range(count)]
    if any(size < reuse or size > stock for size in pool):
        raise DataError('CUT_REMAINDER', '余料超出回用长度范围')
    current = [(size, f'余料{i+1}') for i,size in enumerate(pool)]
    added = loss = 0
    for piece in pieces:
        options = [(size, index) for index,(size,_) in enumerate(current) if size == piece or size >= piece+kerf]
        if options:
            _, index = min(options)
        else:
            added += 1
            current.append((stock, f'新棒{added}'))
            index = len(current)-1
        remaining, label = current[index]
        if remaining != piece and remaining < piece+kerf:
            raise DataError('CUT_KERF', f'{piece} 毫米切件无法容纳锯缝')
        cut_loss = 0 if remaining == piece else kerf
        loss += cut_loss
        current[index] = (remaining-piece-cut_loss, label)
    proof = [('投入新料', added*stock, '毫米'), ('有效切件', sum(pieces), '毫米'), ('锯缝', loss, '毫米')]
    proof += [(f'{label} {"可回用" if size >= reuse else "报废"}', size, '毫米') for size,label in current if size]
    assert sum(pool)+added*stock == sum(pieces)+loss+sum(size for size,_ in current)
    return D(added*stock), proof
