import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "log")
AGENT_LOG_FILENAME = os.path.join(LOG_DIR, "agent.log")
SERVICE_LOG_FILENAME = os.path.join(LOG_DIR, "service.log")

#ENV_DIR = os.path.join(BASE_DIR, "env")
BACKING_MGR_ENV_FILENAME = os.path.join(BASE_DIR, "backing_mgr.env")