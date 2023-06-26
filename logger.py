import logging


def set_logger(
        name: str = __name__, log_level_name: str = "DEBUG") -> logging.Logger:
    """Creates and configures logger instance.

    Args:
        name (str, optional):
            Logger's name. Defaults to __name__.
        log_level_name (str, optional):
            Logging level name ("NOTSET", "DEBUG", "INFO", "WARNING",
            "ERROR", "CRITICAL"). Defaults to "DEBUG".

    Returns:
        logging.Logger: Logger instance
    """
    _log_format = "%(asctime)s - [%(levelname)s] - %(name)s - "\
        "(%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"
    formatter = logging.Formatter(_log_format)
    levels_dict = {"NOTSET": 0, "DEBUG": 10, "INFO": 20, "WARNING": 30,
                   "ERROR": 40, "CRITICAL": 50}
    logger = logging.getLogger(name)

    if log_level_name.upper() in levels_dict:
        log_level = levels_dict[log_level_name]
    else:
        log_level = levels_dict["DEBUG"]

    logging.basicConfig(level=log_level, format=_log_format)
    # logger.setLevel(log_level)
    file_handler = logging.FileHandler(".//logs//last_run.log", "w")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger
