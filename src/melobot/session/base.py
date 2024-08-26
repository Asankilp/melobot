from __future__ import annotations

import asyncio
from asyncio import Condition, Lock
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Generic, cast

from .._ctx import SessionCtx
from ..adapter.model import EventT
from ..exceptions import BotException
from ..typ import AsyncCallable
from .option import Rule

_SESSION_CTX = SessionCtx()


class SessionStateError(BotException):
    def __init__(self, meth: str | None = None, text: str | None = None) -> None:
        if text is not None:
            super().__init__(text)
            return

        super().__init__(f"当前会话状态不支持的操作：{meth}")


class SessionState:
    def __init__(self, session: "Session") -> None:
        self.session = session

    async def work(self, event: EventT) -> None:
        raise SessionStateError(meth=SessionState.work.__name__)

    async def rest(self) -> None:
        raise SessionStateError(meth=SessionState.rest.__name__)

    async def suspend(self, timeout: float | None) -> bool:
        raise SessionStateError(meth=SessionState.suspend.__name__)

    async def wakeup(self, event: EventT) -> None:
        raise SessionStateError(meth=SessionState.wakeup.__name__)

    async def expire(self) -> None:
        raise SessionStateError(meth=SessionState.expire.__name__)


class SpareSessionState(SessionState):
    async def work(self, event: EventT) -> None:
        self.session.event = event
        self.session.to_state(WorkingSessionState)


class WorkingSessionState(SessionState):
    async def rest(self) -> None:
        if self.session.rule is None:
            raise SessionStateError(text="缺少会话规则，会话无法从“运行态”转为“空闲态”")

        cond = self.session.refresh_cond
        async with cond:
            cond.notify()
        self.session.to_state(SpareSessionState)

    async def suspend(self, timeout: float | None) -> bool:
        if self.session.rule is None:
            raise SessionStateError(text="缺少会话规则，会话无法从“运行态”转为“挂起态”")

        cond = self.session.refresh_cond
        async with cond:
            cond.notify()
        self.session.to_state(SuspendSessionState)

        async with self.session.wakeup_cond:
            if timeout is None:
                await self.session.wakeup_cond.wait()
                return True
            try:
                await asyncio.wait_for(self.session.wakeup_cond.wait(), timeout=timeout)
                return True
            except asyncio.TimeoutError:
                return False

    async def expire(self) -> None:
        if self.session.rule is not None:
            cond = self.session.refresh_cond
            async with cond:
                cond.notify()
        self.session.to_state(ExpireSessionState)


class SuspendSessionState(SessionState):

    async def wakeup(self, event: EventT) -> None:
        self.session.event = event
        cond = self.session.wakeup_cond
        async with cond:
            cond.notify()
        self.session.to_state(WorkingSessionState)


class ExpireSessionState(SessionState): ...


class StoreT(dict[str, Any]): ...


class Session(Generic[EventT]):
    __instances__: dict[Rule, set["Session"]] = {}
    __instance_locks__: dict[Rule, Lock] = {}
    __cls_lock__ = Lock()

    def __init__(self, event: EventT, rule: Rule | None, keep: bool = False) -> None:
        self.store: StoreT = StoreT()
        self.event = event
        self.rule = rule
        self.refresh_cond = Condition()
        self.wakeup_cond = Condition()
        self.keep = keep

        self._state: SessionState = WorkingSessionState(self)

    def __lshift__(self, another: "Session") -> None:
        self.store.update(another.store)

    def to_state(self, state_class: type[SessionState]) -> None:
        self._state = state_class(self)

    def on_state(self, state_class: type[SessionState]) -> bool:
        return isinstance(self._state, state_class)

    async def work(self, event: EventT) -> None:
        await self._state.work(event)

    async def rest(self) -> None:
        await self._state.rest()

    async def suspend(self, timeout: float | None = None) -> bool:
        return await self._state.suspend(timeout)

    async def wakeup(self, event: EventT) -> None:
        await self._state.wakeup(event)

    async def expire(self) -> None:
        await self._state.expire()

    @classmethod
    async def get(
        cls,
        event: EventT,
        rule: Rule | None = None,
        wait: bool = True,
        nowait_cb: AsyncCallable[[], None] | None = None,
        keep: bool = False,
    ) -> Session[EventT] | None:
        if rule is None:
            return Session(event, rule=None, keep=keep)

        async with cls.__cls_lock__:
            cls.__instance_locks__.setdefault(rule, Lock())

        async with cls.__instance_locks__[rule]:
            _set = cls.__instances__.setdefault(rule, set())

            suspends = filter(lambda s: s.on_state(SuspendSessionState), _set)
            for session in suspends:
                if await rule.compare(session.event, event):
                    await session.wakeup(event)
                    return None

            spares = filter(lambda s: s.on_state(SpareSessionState), _set)
            for session in spares:
                if await rule.compare(session.event, event):
                    await session.work(event)
                    session.keep = keep
                    return session

            workings = filter(lambda s: s.on_state(WorkingSessionState), _set)
            expires = list(filter(lambda s: s.on_state(ExpireSessionState), _set))
            for session in workings:
                if not await rule.compare(session.event, event):
                    continue

                if not wait:
                    if nowait_cb is not None:
                        await nowait_cb()
                    return None

                cond = session.refresh_cond
                async with cond:
                    await cond.wait()
                    if session.on_state(ExpireSessionState):
                        expires.append(session)
                    elif session.on_state(SuspendSessionState):
                        await session.wakeup(event)
                        return None
                    else:
                        await session.work(event)
                        session.keep = keep
                        return session

            for session in expires:
                Session.__instances__[cast(Rule, session.rule)].remove(session)

            session = Session(event, rule=rule, keep=keep)
            Session.__instances__[rule].add(session)
            return session

    @asynccontextmanager
    async def ctx(self) -> AsyncGenerator[Session[EventT], None]:
        with _SESSION_CTX.on_ctx(self):
            try:
                yield self
            except asyncio.CancelledError:
                if self.on_state(SuspendSessionState):
                    await self.wakeup(self.event)
            finally:
                if self.keep:
                    await self.rest()
                else:
                    await self.expire()


async def suspend(timeout: float | None = None) -> bool:
    return await SessionCtx().get().suspend(timeout)