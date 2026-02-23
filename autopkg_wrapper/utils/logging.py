import logging


def setup_logger(debug=False):
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(filename)s - %(funcName)s - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Suppress jamf_pro_sdk logging unless in debug mode
    # This prevents "__init__.py" log messages from cluttering the output
    if not debug:
        logging.getLogger("jamf_pro_sdk").setLevel(logging.WARNING)

    logging.debug("Debug logging is now enabled")
