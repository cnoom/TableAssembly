"""代码生成器注册表。

设计:生成器是「绑定命名空间的实例」,通过工厂函数创建。
exporter 调用 create_generator(name, namespace) 拿到实例。

新增语言只需:
    1. 实现 CodeGenerator 协议
    2. 写一个工厂函数 namespace -> Generator 实例
    3. 在 GENERATORS 中注册 {name: factory}
exporter 无需改动。
"""
from .base import CodeGenerator, GeneratorFactory, OutputFile, derive_namespace
from .cs import CsGenerator
from .go import GoGenerator
from .java import JavaGenerator
from .lua import LuaGenerator


def _cs_factory(namespace: str) -> CodeGenerator:
    return CsGenerator(namespace)


def _go_factory(namespace: str) -> CodeGenerator:
    return GoGenerator(namespace)


def _java_factory(namespace: str) -> CodeGenerator:
    return JavaGenerator(namespace)


def _lua_factory(namespace: str) -> CodeGenerator:
    return LuaGenerator(namespace)


# 已注册生成器工厂: name -> factory
GENERATORS: dict[str, GeneratorFactory] = {
    "cs": _cs_factory,
    "go": _go_factory,
    "java": _java_factory,
    "lua": _lua_factory,
}


def create_generator(name: str, namespace: str) -> CodeGenerator | None:
    """按名称创建绑定命名空间的生成器。不存在返回 None。"""
    factory = GENERATORS.get(name)
    return factory(namespace) if factory else None


def available_generators() -> list[str]:
    """已注册生成器名列表。"""
    return list(GENERATORS.keys())
