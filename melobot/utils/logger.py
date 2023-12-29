import logging
import logging.config
import logging.handlers
import os

from ..interface.typing import *
from ..interface.utils import Logger, CRITICAL, DEBUG, ERROR, INFO, WARN, WARNING


__all__ = (
    'get_logger'
)


def get_logger(log_dir: str=None, log_level: Literal['DEBUG', 'ERROR', 'INFO', 'WARN', 'WARNING', 'CRITICAL']='DEBUG') -> Logger:
    """
    无日志目录时获取只含 console 输出的 logger，否则返回含文件输出的 logger
    """
    if log_dir:
        if not os.path.exists(log_dir):
            os.mkdir(log_dir)
        config = get_config(log_dir, log_level)
    else:
        config = get_fileless_config(log_level)
    logging.config.dictConfig(config)
    return logging.getLogger('global_logger')


def get_fileless_config(log_level: str):
    """
    返回只含 console 输出的 logger
    """
    config = LOG_CONFIG.copy()
    config['handlers']['console_handler']['level'] = LOG_LEVEL_MAP[log_level]
    return config


def get_config(log_dir: str, log_level: str):
    """
    返回含 console 输出和文件输出的 logger
    """
    config = LOG_CONFIG.copy()
    config['handlers']['console_handler']['level'] = LOG_LEVEL_MAP[log_level]
    config['handlers']['file_handler'] = {
        'class': 'logging.handlers.RotatingFileHandler',  # 必填，处理器对应的类
        'level': logging.DEBUG,  # 选填，处理器的日志级别，可填字符串'info'，或者logging.INFO
        'formatter': 'myformatter2',  # 选填，这里要填写formatters字典中的键
        'filename': os.path.join(log_dir, 'bot.log'),  # filehandler特有参数，文件名
        'maxBytes': 1024*1024,  # 文件大小
        'backupCount': 10,  # 备份数量
        'encoding': 'UTF-8',  # 编码格式
    }
    config['loggers']['global_logger']['handlers'].append('file_handler')
    return config


LOG_COLOR_CONFIG = {
    'DEBUG': 'purple',  # cyan white
    'INFO': 'white',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'bold_red',
}


LOG_LEVEL_MAP = {
    'DEBUG': DEBUG,
    'INFO': INFO,
    'WARN': WARN,
    'WARNING': WARNING,
    'ERROR': ERROR,
    'CRITICAL': CRITICAL,
}


LOG_CONFIG = {
    'version': 1,  # 必填项，值只能为1
    'disable_existing_loggers': True,  # 选填，默认为True，将以向后兼容的方式启用旧行为，此行为是禁用任何现有的非根日志记录器，除非它们或它们的祖先在日志配置中显式命名。如果指定为False，则在进行此调用时存在的记录器将保持启用状态
    'incremental': False,  # 选填，默认为False，作用，为True时，logging完全忽略任何formatters和filters，仅处理handlers的level

    'formatters':  # 格式器配置专用key，在这里配置formatter，可配置复数formatter
        {
            'myformatter1': {
                '()': 'colorlog.ColoredFormatter',  # 必填，格式器对应的类
                'format': '%(log_color)s[%(asctime)s] [%(levelname)s]: %(message)s',  # fmt格式
                'datefmt': '%Y-%m-%d %H:%M:%S',  # 日期时间格式
                'log_colors': LOG_COLOR_CONFIG
            },
            'myformatter2': {
                'class': 'logging.Formatter',  # 将class改为()，代表不使用logging的类，使用我们重新定义的类
                'format': '[%(asctime)s] [%(filename)s %(lineno)d] [%(levelname)s]: %(message)s',  # fmt格式
                'datefmt': '%Y-%m-%d %H:%M:%S'  # 日期时间格式
            }
        },

    'handlers':  # 处理器配置专用key，在这里配置handler，可配置复数handler
        {
            'console_handler': {
                'class': 'logging.StreamHandler',  # 必填，处理器对应的类
                'level': logging.INFO,  # 选填，处理器的日志级别，可填字符串'info'，或者logging.INFO
                'formatter': 'myformatter1',  # 选填，这里要填写formatters字典中的键
            }
        },

    'loggers':  # 记录器配置专用key，在这里配置logger，可配置复数logger
        {
            'global_logger': {
                'handlers': ['console_handler'],  # 列表形式，元素填handlers字典中的handler
                'level': logging.DEBUG,  # 选填，记录器的日志级别，不填则默认Warning级别
                'propagate': False,  # 选填，为False时，禁止将日志消息传递给父级记录器
            }
        },
}
