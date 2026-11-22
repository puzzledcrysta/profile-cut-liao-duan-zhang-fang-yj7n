from decimal import Decimal
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate


def test_reuse_first(cases):
    actual, proof = evaluate(cases['reuse_first'])
    assert actual == Decimal('0')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['锯缝'])) == Decimal('3')


def test_packs_with_kerf(cases):
    actual, proof = evaluate(cases['packs_with_kerf'])
    assert actual == Decimal('12000')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['有效切件'])) == Decimal('12000')


def test_exact_stock(cases):
    actual, proof = evaluate(cases['exact_stock'])
    assert actual == Decimal('6000')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['锯缝'])) == Decimal('0')


def test_kerf_blocks(cases):
    # TRAP-105
    actual, proof = evaluate(cases['kerf_blocks'])
    assert actual == Decimal('12000')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['锯缝'])) == Decimal('6')


def test_best_fit(cases):
    # TRAP-19
    actual, proof = evaluate(cases['best_fit'])
    assert actual == Decimal('0')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['余料2 可回用'])) == Decimal('197')


def test_use_tail(cases):
    actual, proof = evaluate(cases['use_tail'])
    assert actual == Decimal('5000')
    assert Decimal(str(dict((label, value) for label, value, _ in proof)['新棒1 可回用'])) == Decimal('992')


def test_no_kerf_space(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['no_kerf_space'])
    assert error.value.code == 'CUT_KERF'


def test_part_too_long(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['part_too_long'])
    assert error.value.code == 'CUT_SIZE'


def test_invalid_pool(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['invalid_pool'])
    assert error.value.code == 'CUT_REMAINDER'
