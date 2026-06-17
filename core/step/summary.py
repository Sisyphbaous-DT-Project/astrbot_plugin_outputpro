import json
import random
from pathlib import Path

from astrbot.api import logger
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from ..config import PluginConfig
from ..model import OutContext, StepName, StepResult
from .base import BaseStep


class SummaryStep(BaseStep):
    name = StepName.SUMMARY

    def __init__(self, config: PluginConfig):
        super().__init__(config)
        self.cfg = config.summary
        self.quotes = self._load_all_quotes()

    def _load_all_quotes(self) -> list[str]:
        """
        把 summary.quotes 与 summary.quotes_files 里的金句全部合并成一个 list
        """
        raw_quotes = self.cfg.quotes
        raw_files = self.cfg.quotes_files
        if not isinstance(raw_quotes, list):
            logger.warning("[summary] quotes 不是 list，已回退为空列表")
            raw_quotes = []
        if not isinstance(raw_files, list):
            logger.warning("[summary] quotes_files 不是 list，已回退为空列表")
            raw_files = []

        quotes: list[str] = [q for q in raw_quotes if isinstance(q, str)]
        if len(quotes) != len(raw_quotes):
            logger.warning("[summary] quotes 中包含非字符串条目，已自动过滤")

        for file_path in raw_files:
            if not isinstance(file_path, str):
                logger.warning(
                    "[summary] quotes_files 中包含非字符串路径，已跳过：%s",
                    file_path,
                )
                continue
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"金句文件不存在，已跳过：{path}")
                continue
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        file_quotes = [q for q in data if isinstance(q, str)]
                        if len(file_quotes) != len(data):
                            logger.warning(
                                "金句文件包含非字符串条目，已自动过滤：%s",
                                path,
                            )
                        quotes.extend(file_quotes)
                    else:
                        logger.warning(f"金句文件内容不是 list，已跳过：{path}")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("读取金句文件失败 %s: %s", path, e)
        # 合并后去重并保留顺序
        return list(dict.fromkeys(quotes))

    async def handle(self, ctx: OutContext) -> StepResult:
        """图片外显（直接发送并中断流水线）"""
        if (
            isinstance(ctx.event, AiocqhttpMessageEvent)
            and len(ctx.chain) == 1
            and isinstance(ctx.chain[0], Image)
        ):
            if not self.quotes:
                logger.warning("图片外显金句列表为空，已跳过外显")
                return StepResult()

            obmsg = await ctx.event._parse_onebot_json(MessageChain(ctx.chain))
            quote = random.choice(self.quotes)
            obmsg[0]["data"]["summary"] = quote

            await ctx.event.bot.send(ctx.event.message_obj.raw_message, obmsg)  # type: ignore
            ctx.event.should_call_llm(True)
            ctx.chain.clear()

            return StepResult(abort=True, msg=f"已给图片附加外显金句：{quote}")

        return StepResult()
