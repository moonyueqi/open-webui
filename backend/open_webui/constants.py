from enum import Enum


class MESSAGES(str, Enum):
    DEFAULT = lambda msg="": f"{msg if msg else ''}"
    MODEL_ADDED = lambda model="": f"The model '{model}' has been added successfully."
    MODEL_DELETED = (
        lambda model="": f"The model '{model}' has been deleted successfully."
    )


class WEBHOOK_MESSAGES(str, Enum):
    DEFAULT = lambda msg="": f"{msg if msg else ''}"
    USER_SIGNUP = lambda username="": (
        f"New user signed up: {username}" if username else "New user signed up"
    )


class ERROR_MESSAGES(str, Enum):
    def __str__(self) -> str:
        return super().__str__()

    DEFAULT = (
        lambda err="": f'{"出了点问题 :/" if err == "" else "[错误: " + str(err) + "]"}'
    )
    ENV_VAR_NOT_FOUND = "未找到所需的环境变量，程序即将终止。"
    CREATE_USER_ERROR = "创建账户时出现问题，请稍后重试。如果问题仍然存在，请联系系统管理员。"
    DELETE_USER_ERROR = "删除该用户时出现问题，请重试。"
    EMAIL_MISMATCH = "此邮箱与您的提供商注册的邮箱不匹配，请检查邮箱后重试。"
    EMAIL_TAKEN = "此邮箱已被注册，请使用已有账户登录，或使用其他邮箱注册新账户。"
    USERNAME_TAKEN = (
        "此用户名已被注册，请选择其他用户名。"
    )
    PASSWORD_TOO_LONG = "您输入的密码过长，请确保密码长度不超过72字节。"
    COMMAND_TAKEN = "此命令已被注册，请选择其他命令。"
    FILE_EXISTS = "此文件已存在，请选择其他文件。"

    ID_TAKEN = "此ID已被注册，请选择其他ID。"
    MODEL_ID_TAKEN = "此模型ID已被注册，请选择其他模型ID。"
    NAME_TAG_TAKEN = "此名称标签已被注册，请选择其他名称标签。"
    KNOWLEDGE_NAME_TAKEN = "您已有一个同名的知识库，请使用其他名称。"
    KNOWLEDGE_FILE_NAME_TAKEN = "该知识库中已存在同名文件，请重命名后再添加。"
    SKILL_NAME_TAKEN = "已存在同名的技能，请使用其他名称。"
    TOOL_NAME_TAKEN = "已存在同名的工具，请使用其他名称。"
    MODEL_ID_TOO_LONG = "模型ID过长，请确保模型ID长度不超过256个字符。"

    INVALID_TOKEN = (
        "您的会话已过期或令牌无效，请重新登录。"
    )
    INVALID_CRED = "邮箱或密码不正确，请检查是否有拼写错误后重试。"
    INVALID_EMAIL_FORMAT = "您输入的邮箱格式无效，请确认使用的是有效的邮箱地址（例如：yourname@example.com）。"
    INCORRECT_PASSWORD = (
        "密码不正确，请检查是否有拼写错误后重试。"
    )
    INVALID_TRUSTED_HEADER = "您的提供商未提供受信任的头信息，请联系管理员获取帮助。"

    EXISTING_USERS = "由于已有注册用户，无法关闭身份验证。如需禁用WEBUI_AUTH，请确保您的Web界面没有任何已注册用户，且为全新安装。"

    UNAUTHORIZED = "401未授权"
    ACCESS_PROHIBITED = "您没有权限访问此资源，请联系系统管理员获取帮助。"
    ACTION_PROHIBITED = (
        "出于安全考虑，所请求的操作已被限制。"
    )

    FILE_NOT_SENT = "文件未发送"
    FILE_NOT_SUPPORTED = "您尝试上传的文件格式不受支持，请上传支持的格式后重试。"

    NOT_FOUND = "未找到您要查找的内容 :/"
    USER_NOT_FOUND = "未找到该用户 :/"
    API_KEY_NOT_FOUND = "缺少API密钥，请提供有效的API密钥以访问此功能。"
    API_KEY_NOT_ALLOWED = "当前环境未启用API密钥功能。"

    MALICIOUS = "检测到异常活动，请稍后重试。"

    PANDOC_NOT_INSTALLED = "服务器上未安装Pandoc，请联系系统管理员获取帮助。"
    INCORRECT_FORMAT = (
        lambda err="": f"格式无效，请使用正确的格式{err}"
    )
    RATE_LIMIT_EXCEEDED = "API 请求频率超出限制"

    MODEL_NOT_FOUND = lambda name="": f"未找到模型 '{name}'"
    OPENAI_NOT_FOUND = lambda name="": "未找到OpenAI API"
    OLLAMA_NOT_FOUND = "WebUI无法连接到Ollama"
    CREATE_API_KEY_ERROR = "创建 API 密钥时出现问题，请稍后重试。如果问题持续存在，请联系系统管理员获取帮助。"
    API_KEY_CREATION_NOT_ALLOWED = "当前环境不允许创建API密钥。"

    EMPTY_CONTENT = "提供的内容为空，请确保存在文本或数据后再继续。"

    DB_NOT_SQLITE = "此功能仅在使用SQLite数据库时可用。"

    INVALID_URL = (
        "您提供的 URL 无效，请仔细检查后重试。"
    )

    WEB_SEARCH_ERROR = (
        lambda err="": f"{err if err else '网络搜索时出现问题，请稍后重试。'}"
    )

    OLLAMA_API_DISABLED = (
        "Ollama API 已被禁用，请启用后再使用此功能。"
    )

    FILE_TOO_LARGE = (
        lambda size="": f"当前上传的文件过大，请上传小于{size}的文件。"
    )

    DUPLICATE_CONTENT = (
        "检测到重复内容，请提供唯一的内容后继续。"
    )
    FILE_NOT_PROCESSED = "此文件的提取内容不可用，请确保文件已处理后再继续。"

    INVALID_PASSWORD = lambda err="": (
        err if err else "密码不符合所要求的验证条件。"
    )

    # ===== 嵌入 / 重排序 / 检索 =====
    EMBEDDING_MODEL_UNAVAILABLE = (
        "嵌入模型暂时不可用，请联系管理员检查 API 配置。"
    )
    EMBEDDING_NOT_CONFIGURED = (
        "嵌入模型尚未配置或调用失败，请联系管理员检查嵌入模型设置和 API 连通性。"
    )
    EMBEDDING_COUNT_MISMATCH = (
        lambda got=0, expected=0: f"嵌入向量数量不一致（实际 {got}，预期 {expected}），部分批次调用可能失败，请联系管理员查看日志。"
    )
    RERANKING_MODEL_UNAVAILABLE = (
        "重排序模型暂时不可用，请联系管理员检查 API 配置。"
    )
    RAG_RETRIEVAL_FAILED = (
        "知识库检索失败，请联系管理员检查嵌入模型 API 配置。"
    )
    INVALID_TEXT_SPLITTER = "文本切分方式无效，请联系管理员检查知识库切分配置。"
    VECTOR_DB_SAVE_FAILED = "保存到向量数据库失败，请稍后重试或联系管理员。"

    # ===== 联网搜索 =====
    WEB_SEARCH_NO_RESULTS = "未在网络搜索中找到相关结果，请尝试更换关键词后重试。"
    WEB_SEARCH_KEY_MISSING = (
        lambda engine="": f"未配置{(' ' + engine) if engine else ''}搜索引擎所需的密钥或地址，请联系管理员完善配置。"
    )

    # ===== 语音模型（STT / TTS）=====
    STT_FAILED = "语音转文字失败，请联系管理员检查 STT API 配置。"
    TTS_FAILED = "语音合成失败，请联系管理员检查 TTS API 配置。"
    STT_CONFIG_MISSING = (
        lambda provider="": f"{provider + ' ' if provider else ''}语音识别未正确配置，请联系管理员。"
    )
    TTS_CONFIG_MISSING = (
        lambda provider="": f"{provider + ' ' if provider else ''}语音合成未正确配置，请联系管理员。"
    )
    AUDIO_FILE_TOO_LARGE = (
        lambda size="": f"音频文件过大{f'（限制 {size}）' if size else ''}，请上传更小的文件。"
    )
    AUDIO_FORMAT_INVALID = "音频格式不支持，请上传 mp3 或 wav 格式。"
    AUDIO_FILE_NOT_FOUND = "音频文件未找到，请重新录制后再试。"
    INVALID_AUDIO_PAYLOAD = "请求格式无效，请联系管理员。"
    INVALID_VOICE_ID = "语音 ID 无效，请联系管理员检查 TTS 配置。"


class TASKS(str, Enum):
    def __str__(self) -> str:
        return super().__str__()

    DEFAULT = lambda task="": f"{task if task else 'generation'}"
    TITLE_GENERATION = "title_generation"
    FOLLOW_UP_GENERATION = "follow_up_generation"
    TAGS_GENERATION = "tags_generation"
    EMOJI_GENERATION = "emoji_generation"
    QUERY_GENERATION = "query_generation"
    IMAGE_PROMPT_GENERATION = "image_prompt_generation"
    AUTOCOMPLETE_GENERATION = "autocomplete_generation"
    FUNCTION_CALLING = "function_calling"
    MOA_RESPONSE_GENERATION = "moa_response_generation"
