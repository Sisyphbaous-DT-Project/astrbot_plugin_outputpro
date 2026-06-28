from astrbot.core.message.components import (
    At,
    BaseMessageComponent,
    Face,
    Image,
    Plain,
    Reply,
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from ..config import PluginConfig
from ..model import OutContext, StepName, StepResult
from .base import BaseStep


class ReplyStep(BaseStep):
    name = StepName.REPLY
    unsupported_platforms = {"dingtalk"}

    def __init__(self, config: PluginConfig):
        super().__init__(config)
        self.cfg = config.reply

    async def handle(self, ctx: OutContext) -> StepResult:
        platform_name = ctx.event.get_platform_name()
        if platform_name in self.unsupported_platforms:
            return StepResult(msg=f"平台不支持智能引用，已跳过: {platform_name}")
        if not ctx.gid:
            return StepResult()

        threshold = int(self.cfg.threshold or 0)
        if threshold <= 0:
            return StepResult(msg="智能引用已关闭，跳过")

        msg_id = str(ctx.event.message_obj.message_id)
        if any(isinstance(x, Reply) for x in ctx.chain):
            return StepResult(msg=f"智能引用跳过：已有Reply组件, msg_id={msg_id}")

        unsupported = self._first_unsupported_component(ctx.chain)
        if unsupported is not None:
            return StepResult(
                msg=(
                    "智能引用跳过：消息链包含不支持前置引用的组件, "
                    f"msg_id={msg_id}, component={type(unsupported).__name__}"
                ),
            )

        queue = ctx.group.msg_queue
        queue_str = [str(x) for x in queue]
        if msg_id not in queue_str:
            return StepResult(
                msg=f"智能引用跳过：触发消息不在队列中, msg_id={msg_id}, queue_len={len(queue_str)}",
            )

        if msg_id in {str(x) for x in ctx.group.recent_replied_msg_ids}:
            return StepResult(
                msg=f"智能引用跳过：触发消息已处理过, msg_id={msg_id}, queue_len={len(queue_str)}",
            )

        idx = queue_str.index(msg_id)
        pushed = len(queue_str) - idx - 1
        if pushed < threshold:
            return StepResult(
                msg=(
                    "智能引用跳过：插入消息数未达阈值, "
                    f"msg_id={msg_id}, pushed={pushed}, threshold={threshold}, queue_len={len(queue_str)}"
                ),
            )

        ctx.chain.insert(0, Reply(id=msg_id))
        if self.cfg.include_at and isinstance(ctx.event, AiocqhttpMessageEvent):
            ctx.chain.insert(1, At(qq=ctx.event.get_sender_id()))
            # 在 At 后添加带零宽空格包裹的空格，确保与后续内容有间距
            ctx.chain.insert(2, Plain(text="\u200b \u200b"))
        ctx.group.recent_replied_msg_ids.append(msg_id)
        return StepResult(
            msg=(
                "已插入Reply组件, "
                f"引用消息{msg_id}, pushed={pushed}, threshold={threshold}, queue_len={len(queue_str)}"
            ),
        )

    @staticmethod
    def _first_unsupported_component(
        chain: list[BaseMessageComponent],
    ) -> BaseMessageComponent | None:
        supported_types = (Plain, Image, Face, At)
        for comp in chain:
            if not isinstance(comp, supported_types):
                return comp
        return None
