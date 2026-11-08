import pandas as pd
import pytest
from src.scenarios import KINDS, scenario_suite, scenario_features
from test_weather_model import history


def test_scenarios_cover_taxonomy_replay_and_do_not_change_raw():
    raw=history(240)
    before=raw.copy(deep=True)
    first,manifest=scenario_suite(raw,seed=7,contexts_per_kind=2,partition='development')
    replay,again=scenario_suite(raw,seed=7,contexts_per_kind=2,partition='development')
    pd.testing.assert_frame_equal(raw,before)
    pd.testing.assert_frame_equal(first,replay)
    assert manifest==again
    assert set(first.kind)==set(KINDS)
    assert len(manifest)==len(KINDS)*2
    assert not {'event_id','kind','anomaly_class','anomaly_reason','timestamp'} & set(scenario_features(first))
    assert all(m['edits'] for m in manifest if m['kind']!='normal')


def test_partition_source_windows_do_not_cross_boundaries():
    raw=history(360)
    train,tm=scenario_suite(raw.iloc[:180],seed=7,contexts_per_kind=2,partition='train')
    test,vm=scenario_suite(raw.iloc[180:],seed=9,contexts_per_kind=2,partition='test')
    assert max(pd.Timestamp(m['source_end']) for m in tm) < min(pd.Timestamp(m['source_start']) for m in vm)
    assert not set(train.event_id)&set(test.event_id)


def test_insufficient_context_is_not_silently_replaced():
    with pytest.raises(ValueError,match='konteks'):
        scenario_suite(history(60),seed=7,contexts_per_kind=50,partition='small')
