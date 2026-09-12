"""Strict slot-start Q3 control; revisions cannot rewrite settled slots."""
from datetime import timedelta
import numpy as np
from src.core.model import vector
from src.q2.forecast import check_time
from src.q2.strict_execution import StrictExecutor


class StrictRollingExecutor(StrictExecutor):
    def __init__(self, **kwargs):
        if kwargs.get('mode', 'B0') != 'B0':
            raise ValueError('This experiment uses the same greedy controller throughout')
        super().__init__(**kwargs)
        self.last_revision_slot = 0

    def revise(self, *, commitment, remaining_load, remaining_pv, decision_time, forecast_available_at):
        check_time(decision_time)
        check_time(forecast_available_at)
        i = len(self.records)
        if (i not in (36,72,108) or i <= self.last_revision_slot or self.pending is not None or
                decision_time != self.start+timedelta(minutes=10*i)):
            raise ValueError('Revision must precede the first command at an unused 06/12/18 boundary')
        if forecast_available_at > decision_time or forecast_available_at < self.forecast_available_at:
            raise ValueError('Future or older forecast cannot replace current information')
        g=vector(commitment,'new commitment',144)
        if not np.array_equal(g[:i],self.g[:i]):
            raise ValueError('Past contracts are immutable')
        load=vector(remaining_load,'remaining load',144-i)
        pv=vector(remaining_pv,'remaining PV',144-i)
        delta=g-self.g
        self.load=vector(np.r_[self.load[:i],load],'load',144)
        self.pv=vector(np.r_[self.pv[:i],pv],'pv',144)
        self.g=g
        self.forecast_available_at=forecast_available_at
        self.last_revision_slot=i
        return {'increase_kwh':float(np.maximum(delta,0).sum()),
                'decrease_kwh':float(np.maximum(-delta,0).sum())}
