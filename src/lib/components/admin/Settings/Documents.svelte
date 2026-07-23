<script lang="ts">
	import { toast } from 'svelte-sonner';

	import { onMount, getContext, createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher();

	import {
		getQuerySettings,
		updateQuerySettings,
		resetVectorDB,
		getEmbeddingConfig,
		updateEmbeddingConfig,
		getRerankingConfig,
		updateRerankingConfig,
		getRAGConfig,
		updateRAGConfig,
		verifyEmbeddingModel,
		verifyRerankerModel,
		type ModelVerifyResult
	} from '$lib/apis/retrieval';

	import { reindexKnowledgeFiles } from '$lib/apis/knowledge';
	import { deleteAllFiles } from '$lib/apis/files';
	import { verifyOpenAIConnection } from '$lib/apis/openai';
	import { verifyPreprocessService } from '$lib/apis/documentPreprocessing';

	import ResetUploadDirConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import ResetVectorDBConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import ReindexKnowledgeFilesConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	let updateEmbeddingModelLoading = false;
	let updateRerankingModelLoading = false;

	let verifyingEmbedding = false;
	let verifyingReranker = false;
	let verifyingPreprocessService = false;
	let verifyingEnrich = false;

	// 从 verifyOpenAIConnection 抛出的字符串里提取 HTTP 状态码。
	// 字符串约定形如 "OpenAI: [401] xxx" / "OpenAI: [404] xxx" / "OpenAI: Network Problem"。
	const extractHttpStatus = (err: unknown): number | null => {
		const m = `${err ?? ''}`.match(/\[(\d{3})\]/);
		return m ? Number(m[1]) : null;
	};

	// 把 verifyOpenAIConnection 抛出的错误统一翻译成面向用户的友好文案。
	const classifyVerifyError = (err: unknown): string => {
		const status = extractHttpStatus(err);
		const msg = `${err ?? ''}`.toLowerCase();
		if (status === 401 || status === 403 || msg.includes('unauthorized')) {
			return $i18n.t('API key is missing, invalid, or has no permission');
		}
		if (status === 404) {
			return $i18n.t('Endpoint not found, please check the URL');
		}
		if (status === 408 || msg.includes('timed out') || msg.includes('timeout')) {
			return $i18n.t('Request timed out, please try again later');
		}
		// 任何其他状态码或纯网络异常都归为"连不上服务器"。
		return $i18n.t('Cannot reach the server, please check the URL or your network');
	};

	// 上游 4xx 经常用 "insufficient balance / quota / 余额 / 欠费 / payment" 等字样来表达账户没钱，
	// 这跟 "key 无权限" 是两件事，单独识别一下，避免用户去白排查 key。
	const looksLikeBalanceIssue = (message?: string): boolean => {
		if (!message) return false;
		const m = message.toLowerCase();
		return (
			m.includes('balance') ||
			m.includes('insufficient') ||
			m.includes('quota') ||
			m.includes('exceeded') ||
			m.includes('payment') ||
			m.includes('billing') ||
			message.includes('余额') ||
			message.includes('欠费') ||
			message.includes('额度')
		);
	};

	// Translate a structured model-verify result into a friendly Chinese-ready toast.
	const showModelVerifyError = (result: ModelVerifyResult, modelName: string) => {
		const stage = result.stage ?? 'model';
		// auth 阶段优先识别"余额不足"，命中就单独提示，否则再回退到通用密钥错误文案。
		if (stage === 'auth' && looksLikeBalanceIssue(result.message)) {
			toast.error($i18n.t('API balance is insufficient or quota has been used up'));
			return;
		}
		const map: Record<string, string> = {
			connection: $i18n.t('Cannot reach the server, please check the URL or your network'),
			// 同时覆盖"未填 key"和"key 错/无权限"两种 401/403 场景，避免误导用户去查网络。
			auth: $i18n.t('API key is missing, invalid, or has no permission'),
			endpoint: $i18n.t('Endpoint not found, please check the URL'),
			timeout: $i18n.t('Request timed out, please try again later'),
			model: $i18n.t('Model "{{model}}" is unavailable, please check the model name', {
				model: modelName
			}),
			input: $i18n.t('Please fill in URL and model name')
		};
		toast.error(map[stage] ?? map.model);
	};

	const runVerifyEmbedding = async () => {
		verifyingEmbedding = true;
		try {
			const conn = await verifyOpenAIConnection(localStorage.token, {
				url: OpenAIUrl.replace(/\/$/, ''),
				key: OpenAIKey,
				config: { auth_type: 'bearer' }
			}).catch((err) => {
				toast.error(classifyVerifyError(err));
				return null;
			});
			if (!conn) return;

			const result = await verifyEmbeddingModel(localStorage.token, {
				url: OpenAIUrl.replace(/\/$/, ''),
				key: OpenAIKey ?? '',
				model: RAG_EMBEDDING_MODEL
			});

			if (result.ok) {
				toast.success(
					$i18n.t('Verified: model "{{model}}" is available', { model: RAG_EMBEDDING_MODEL })
				);
			} else {
				showModelVerifyError(result, RAG_EMBEDDING_MODEL);
			}
		} finally {
			verifyingEmbedding = false;
		}
	};

	const verifyEmbeddingHandler = async () => {
		if (!OpenAIUrl) {
			toast.error($i18n.t('URL is required'));
			return;
		}
		if (!RAG_EMBEDDING_MODEL) {
			toast.error($i18n.t('Please fill in the embedding model name first'));
			return;
		}

		// 即使 API Key 为空也直接验证：部分自部署/本地服务（如 Ollama）允许无鉴权；
		// 真的需要 key 的上游会返回 401/403，会被翻译成"API 密钥未填写、无效或没有权限"。
		await runVerifyEmbedding();
	};

	const runVerifyReranker = async () => {
		const rerankerModelName = RAGConfig?.RAG_RERANKING_MODEL ?? '';
		verifyingReranker = true;
		try {
			const conn = await verifyOpenAIConnection(localStorage.token, {
				url: RAGConfig.RAG_EXTERNAL_RERANKER_URL.replace(/\/$/, ''),
				key: RAGConfig.RAG_EXTERNAL_RERANKER_API_KEY ?? '',
				config: { auth_type: 'bearer' }
			}).catch((err) => {
				const status = extractHttpStatus(err);
				// Reranker endpoints often don't expose /models, so we treat 404 as
				// "connection ok, skip step 1" and continue to the real rerank call.
				if (status === 404) {
					return { _skipped: true };
				}
				toast.error(classifyVerifyError(err));
				return null;
			});
			if (!conn) return;

			const result = await verifyRerankerModel(localStorage.token, {
				url: RAGConfig.RAG_EXTERNAL_RERANKER_URL.replace(/\/$/, ''),
				key: RAGConfig.RAG_EXTERNAL_RERANKER_API_KEY ?? '',
				model: rerankerModelName,
				timeout: RAGConfig.RAG_EXTERNAL_RERANKER_TIMEOUT
					? Number(RAGConfig.RAG_EXTERNAL_RERANKER_TIMEOUT)
					: null
			});

			if (result.ok) {
				toast.success(
					$i18n.t('Verified: model "{{model}}" is available', { model: rerankerModelName })
				);
			} else {
				showModelVerifyError(result, rerankerModelName);
			}
		} finally {
			verifyingReranker = false;
		}
	};

	const verifyRerankerHandler = async () => {
		if (!RAGConfig?.RAG_EXTERNAL_RERANKER_URL) {
			toast.error($i18n.t('URL is required'));
			return;
		}
		const rerankerModelName = RAGConfig?.RAG_RERANKING_MODEL ?? '';
		if (!rerankerModelName) {
			toast.error($i18n.t('Please fill in the reranker model name first'));
			return;
		}

		// 不再为"未填 key"弹确认框，直接发请求；上游 401/403 会得到正确的鉴权错误提示。
		await runVerifyReranker();
	};

	const verifyPreprocessServiceHandler = async () => {
		if (!RAGConfig?.DOC_PREPROCESS_SERVICE_URL) {
			toast.error($i18n.t('URL is required'));
			return;
		}
		verifyingPreprocessService = true;
		try {
			const res = await verifyPreprocessService(localStorage.token).catch((err) => {
				toast.error(`${err}`);
				return null;
			});
			if (res?.status) {
				toast.success($i18n.t('Preprocessing service is reachable'));
			}
		} finally {
			verifyingPreprocessService = false;
		}
	};

	const verifyEnrichHandler = async () => {
		if (!RAGConfig?.DOC_PREPROCESS_ENRICH_BASE_URL) {
			toast.error($i18n.t('URL is required'));
			return;
		}
		const model = RAGConfig?.DOC_PREPROCESS_ENRICH_MODEL ?? '';
		if (!model) {
			toast.error($i18n.t('Please fill in the model name first'));
			return;
		}
		verifyingEnrich = true;
		try {
			const conn = await verifyOpenAIConnection(localStorage.token, {
				url: RAGConfig.DOC_PREPROCESS_ENRICH_BASE_URL.replace(/\/$/, ''),
				key: RAGConfig.DOC_PREPROCESS_ENRICH_API_KEY ?? '',
				config: { auth_type: 'bearer' }
			}).catch((err) => {
				toast.error(classifyVerifyError(err));
				return null;
			});
			if (!conn) return;
			toast.success($i18n.t('Verified: model "{{model}}" is available', { model }));
		} finally {
			verifyingEnrich = false;
		}
	};

	let showResetConfirm = false;
	let showResetUploadDirConfirm = false;
	let showReindexConfirm = false;

	let RAG_EMBEDDING_ENGINE = 'openai';
	let RAG_EMBEDDING_MODEL = '';
	let RAG_EMBEDDING_BATCH_SIZE = 1;
	let ENABLE_ASYNC_EMBEDDING = true;
	let RAG_EMBEDDING_CONCURRENT_REQUESTS = 0;

	let OpenAIUrl = '';
	let OpenAIKey = '';

	let AzureOpenAIUrl = '';
	let AzureOpenAIKey = '';
	let AzureOpenAIVersion = '';

	let OllamaUrl = '';
	let OllamaKey = '';

	// 加载完成后保留一份"嵌入相关原始值"快照，
	// 提交时若所有字段都没变化，直接跳过 /embedding/update，
	// 避免后端重新构造 embedding function（较慢）以及无意义的写库。
	let embeddingSnapshot: Record<string, any> | null = null;

	const buildEmbeddingFingerprint = () => ({
		RAG_EMBEDDING_ENGINE,
		RAG_EMBEDDING_MODEL,
		RAG_EMBEDDING_BATCH_SIZE,
		ENABLE_ASYNC_EMBEDDING,
		RAG_EMBEDDING_CONCURRENT_REQUESTS,
		OpenAIUrl,
		OpenAIKey,
		OllamaUrl,
		OllamaKey,
		AzureOpenAIUrl,
		AzureOpenAIKey,
		AzureOpenAIVersion
	});

	let querySettings = {
		template: '',
		r: 0.0,
		k: 4,
		k_reranker: 4,
		hybrid: false
	};

	let RAGConfig = null;

	const embeddingModelUpdateHandler = async () => {
		if (RAG_EMBEDDING_ENGINE === '' && RAG_EMBEDDING_MODEL.split('/').length - 1 > 1) {
			toast.error(
				$i18n.t(
					'Model filesystem path detected. Model shortname is required for update, cannot continue.'
				)
			);
			return;
		}
		if (RAG_EMBEDDING_ENGINE === 'ollama' && RAG_EMBEDDING_MODEL === '') {
			toast.error(
				$i18n.t(
					'Model filesystem path detected. Model shortname is required for update, cannot continue.'
				)
			);
			return;
		}

		if (RAG_EMBEDDING_ENGINE === 'openai' && RAG_EMBEDDING_MODEL === '') {
			toast.error(
				$i18n.t(
					'Model filesystem path detected. Model shortname is required for update, cannot continue.'
				)
			);
			return;
		}

		if (
			RAG_EMBEDDING_ENGINE === 'azure_openai' &&
			(AzureOpenAIKey === '' || AzureOpenAIUrl === '' || AzureOpenAIVersion === '')
		) {
			toast.error($i18n.t('OpenAI URL/Key required.'));
			return;
		}

		console.debug('Update embedding model attempt:', {
			RAG_EMBEDDING_ENGINE,
			RAG_EMBEDDING_MODEL,
			RAG_EMBEDDING_BATCH_SIZE,
			ENABLE_ASYNC_EMBEDDING,
			RAG_EMBEDDING_CONCURRENT_REQUESTS
		});

		updateEmbeddingModelLoading = true;
		const res = await updateEmbeddingConfig(localStorage.token, {
			RAG_EMBEDDING_ENGINE: RAG_EMBEDDING_ENGINE,
			RAG_EMBEDDING_MODEL: RAG_EMBEDDING_MODEL,
			RAG_EMBEDDING_BATCH_SIZE: RAG_EMBEDDING_BATCH_SIZE,
			ENABLE_ASYNC_EMBEDDING: ENABLE_ASYNC_EMBEDDING,
			RAG_EMBEDDING_CONCURRENT_REQUESTS: RAG_EMBEDDING_CONCURRENT_REQUESTS,
			ollama_config: {
				key: OllamaKey,
				url: OllamaUrl
			},
			openai_config: {
				key: OpenAIKey,
				url: OpenAIUrl
			},
			azure_openai_config: {
				key: AzureOpenAIKey,
				url: AzureOpenAIUrl,
				version: AzureOpenAIVersion
			}
		}).catch(async (error) => {
			toast.error(`${error}`);
			await setEmbeddingConfig();
			return null;
		});
		updateEmbeddingModelLoading = false;

		if (res) {
			console.debug('embeddingModelUpdateHandler:', res);
		}
	};

	// 判断当前嵌入模型配置是否填写完整（未填则视为"不使用此功能"，保存时静默跳过嵌入更新，
	// 不阻断文档预处理等其他设置的保存）。
	const isEmbeddingConfigured = () => {
		if (RAG_EMBEDDING_ENGINE === 'azure_openai') {
			return !!(AzureOpenAIKey && AzureOpenAIUrl && AzureOpenAIVersion);
		}
		// openai / ollama / 本地引擎：至少要有模型名
		return !!RAG_EMBEDDING_MODEL;
	};

	const submitHandler = async () => {
		// 嵌入模型相关字段走 /embedding/update（独立接口）；
		// 仅在用户实际修改了嵌入相关字段、且嵌入配置填写完整时才调用，
		// 避免后端重新构造 embedding function，也避免未配置嵌入时阻断其他设置的保存。
		if (!RAGConfig.BYPASS_EMBEDDING_AND_RETRIEVAL && isEmbeddingConfigured()) {
			const currentFingerprint = buildEmbeddingFingerprint();
			const embeddingChanged =
				!embeddingSnapshot ||
				JSON.stringify(currentFingerprint) !== JSON.stringify(embeddingSnapshot);

			if (embeddingChanged) {
				await embeddingModelUpdateHandler();
				embeddingSnapshot = currentFingerprint;
			}
		}

		// 仅提交当前 UI 中实际出现的字段，避免把已注释隐藏的旧值原样回写数据库，
		// 减少 PersistentConfig 重复写盘带来的"保存很慢"问题。
		const payload = {
			// Chunking
			CHUNK_SIZE: RAGConfig.CHUNK_SIZE,
			CHUNK_OVERLAP: RAGConfig.CHUNK_OVERLAP,
			CHUNK_MIN_SIZE_TARGET: RAGConfig.CHUNK_MIN_SIZE_TARGET,

			// Reranking Model
			RAG_RERANKING_MODEL: RAGConfig.RAG_RERANKING_MODEL,
			RAG_RERANKING_BATCH_SIZE: RAGConfig.RAG_RERANKING_BATCH_SIZE,
			RAG_EXTERNAL_RERANKER_URL: RAGConfig.RAG_EXTERNAL_RERANKER_URL,
			RAG_EXTERNAL_RERANKER_API_KEY: RAGConfig.RAG_EXTERNAL_RERANKER_API_KEY,

			// Search Parameters
			TOP_K: RAGConfig.TOP_K,
			TOP_K_RERANKER: RAGConfig.TOP_K_RERANKER,
			RELEVANCE_THRESHOLD: RAGConfig.RELEVANCE_THRESHOLD,
			HYBRID_BM25_WEIGHT: RAGConfig.HYBRID_BM25_WEIGHT,

			// RAG Template
			RAG_TEMPLATE: RAGConfig.RAG_TEMPLATE,

			// Document preprocessing (meteokb)
			DOC_PREPROCESS_SERVICE_URL: RAGConfig.DOC_PREPROCESS_SERVICE_URL,
			DOC_PREPROCESS_ENRICH_ENABLED: RAGConfig.DOC_PREPROCESS_ENRICH_ENABLED,
			DOC_PREPROCESS_ENRICH_BASE_URL: RAGConfig.DOC_PREPROCESS_ENRICH_BASE_URL,
			DOC_PREPROCESS_ENRICH_API_KEY: RAGConfig.DOC_PREPROCESS_ENRICH_API_KEY,
			DOC_PREPROCESS_ENRICH_MODEL: RAGConfig.DOC_PREPROCESS_ENRICH_MODEL,
			// 不再暴露默认区域：文档无地名时 region 留空
			DOC_PREPROCESS_ENRICH_DEFAULT_REGION: ''
		};

		const res = await updateRAGConfig(localStorage.token, payload).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
		if (res) {
			dispatch('save');
		}
	};

	const setEmbeddingConfig = async () => {
		const embeddingConfig = await getEmbeddingConfig(localStorage.token);

		if (embeddingConfig) {
			// 强制使用 openai 嵌入引擎，UI 不再提供其他引擎选项
			RAG_EMBEDDING_ENGINE = 'openai';
			RAG_EMBEDDING_MODEL = embeddingConfig.RAG_EMBEDDING_MODEL;
			RAG_EMBEDDING_BATCH_SIZE = embeddingConfig.RAG_EMBEDDING_BATCH_SIZE ?? 1;
			ENABLE_ASYNC_EMBEDDING = embeddingConfig.ENABLE_ASYNC_EMBEDDING ?? true;
			RAG_EMBEDDING_CONCURRENT_REQUESTS = embeddingConfig.RAG_EMBEDDING_CONCURRENT_REQUESTS ?? 0;

			OpenAIKey = embeddingConfig.openai_config.key;
			OpenAIUrl = embeddingConfig.openai_config.url;

			OllamaKey = embeddingConfig.ollama_config.key;
			OllamaUrl = embeddingConfig.ollama_config.url;

			AzureOpenAIKey = embeddingConfig.azure_openai_config.key;
			AzureOpenAIUrl = embeddingConfig.azure_openai_config.url;
			AzureOpenAIVersion = embeddingConfig.azure_openai_config.version;

			embeddingSnapshot = buildEmbeddingFingerprint();
		}
	};
	onMount(async () => {
		await setEmbeddingConfig();

		const config = await getRAGConfig(localStorage.token);
		config.ALLOWED_FILE_EXTENSIONS = (config?.ALLOWED_FILE_EXTENSIONS ?? []).join(', ');

		config.DOCLING_PARAMS =
			typeof config.DOCLING_PARAMS === 'object'
				? JSON.stringify(config.DOCLING_PARAMS ?? {}, null, 2)
				: config.DOCLING_PARAMS;

		config.MINERU_PARAMS =
			typeof config.MINERU_PARAMS === 'object'
				? JSON.stringify(config.MINERU_PARAMS ?? {}, null, 2)
				: config.MINERU_PARAMS;

		RAGConfig = config;
	});
</script>

<ResetUploadDirConfirmDialog
	bind:show={showResetUploadDirConfirm}
	on:confirm={async () => {
		const res = await deleteAllFiles(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Success'));
		}
	}}
/>

<ResetVectorDBConfirmDialog
	bind:show={showResetConfirm}
	on:confirm={() => {
		const res = resetVectorDB(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Success'));
		}
	}}
/>

<ReindexKnowledgeFilesConfirmDialog
	bind:show={showReindexConfirm}
	on:confirm={async () => {
		const res = await reindexKnowledgeFiles(localStorage.token).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Success'));
		}
	}}
/>

<form
	class="flex flex-col h-full justify-between space-y-3 text-sm"
	on:submit|preventDefault={() => {
		submitHandler();
	}}
>
	{#if RAGConfig}
		<div class="space-y-5 overflow-y-scroll scrollbar-hidden h-full pr-1.5">
			{#if false}
			<!-- Document chunking (Document Settings 节已合并到 Embedding；保留代码以便恢复) -->
			<div>
				<div class="flex justify-between items-center mt-0.5 mb-2.5 gap-2">
					<div class="text-base font-medium shrink-0">{$i18n.t('Document Settings')}</div>

					<div class="flex items-center gap-1.5 min-w-0">
						<Tooltip
							content={$i18n.t(
								'These settings are shared across all users in this workspace.'
							)}
						>
							<div
								class="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500 cursor-help truncate"
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 20 20"
									fill="currentColor"
									class="size-3.5 shrink-0"
									aria-hidden="true"
								>
									<path
										fill-rule="evenodd"
										d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Zm-7-4a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM9 9a.75.75 0 0 0 0 1.5h.253a.25.25 0 0 1 .244.304l-.459 2.066A1.75 1.75 0 0 0 10.747 15H11a.75.75 0 0 0 0-1.5h-.253a.25.25 0 0 1-.244-.304l.459-2.066A1.75 1.75 0 0 0 9.253 9H9Z"
										clip-rule="evenodd"
									/>
								</svg>
								<span class="truncate">{$i18n.t('Shared with all users')}</span>
							</div>
						</Tooltip>
					</div>
				</div>

				<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

					<!-- 注释掉：内容提取引擎选项、PDF OCR、PDF Loader Mode、Datalab Marker、External、Tika、Docling、Document Intelligence、Mistral OCR、MinerU 等 -->
					{#if false}
					<div class="mb-2.5 flex flex-col w-full justify-between">
						<div class="flex w-full justify-between mb-1">
							<div class="self-center text-xs font-medium">
								{$i18n.t('Content Extraction Engine')}
							</div>
							<div class="">
								<select
									class="w-fit pr-8 rounded-sm px-2 text-xs bg-transparent outline-hidden text-right"
									bind:value={RAGConfig.CONTENT_EXTRACTION_ENGINE}
								>
									<option value="">{$i18n.t('Default')}</option>
									<option value="external">{$i18n.t('External')}</option>
									<option value="tika">{$i18n.t('Tika')}</option>
									<option value="docling">{$i18n.t('Docling')}</option>
									<option value="datalab_marker">{$i18n.t('Datalab Marker API')}</option>
									<option value="document_intelligence">{$i18n.t('Document Intelligence')}</option>
									<option value="mistral_ocr">{$i18n.t('Mistral OCR')}</option>
									<option value="mineru">{$i18n.t('MinerU')}</option>
								</select>
							</div>
						</div>

						{#if RAGConfig.CONTENT_EXTRACTION_ENGINE === ''}
							<div class="flex w-full mt-1">
								<div class="flex-1 flex justify-between">
									<div class=" self-center text-xs font-medium">
										{$i18n.t('PDF Extract Images (OCR)')}
									</div>
									<div class="flex items-center relative">
										<Switch bind:state={RAGConfig.PDF_EXTRACT_IMAGES} />
									</div>
								</div>
							</div>

							<div class="flex w-full mt-2">
								<div class="flex-1 flex justify-between">
									<div class=" self-center text-xs font-medium">
										<Tooltip
											content={$i18n.t(
												'Page mode creates one document per page. Single mode combines all pages into one document for better chunking across page boundaries.'
											)}
											placement="top-start"
										>
											{$i18n.t('PDF Loader Mode')}
										</Tooltip>
									</div>
									<div class="">
										<select
											class="w-fit pr-8 rounded-sm px-2 text-xs bg-transparent outline-hidden text-right"
											bind:value={RAGConfig.PDF_LOADER_MODE}
										>
											<option value="page">{$i18n.t('Page')}</option>
											<option value="single">{$i18n.t('Single')}</option>
										</select>
									</div>
								</div>
							</div>
						{:else if RAGConfig.CONTENT_EXTRACTION_ENGINE === 'datalab_marker'}
							<div class="my-0.5 flex gap-2 pr-2">
								<Tooltip
									content={$i18n.t(
										'API Base URL for Datalab Marker service. Defaults to: https://www.datalab.to/api/v1/marker'
									)}
									placement="top-start"
									className="w-full"
								>
									<input
										class="flex-1 w-full text-sm bg-transparent outline-hidden"
										placeholder={$i18n.t('Enter Datalab Marker API Base URL')}
										bind:value={RAGConfig.DATALAB_MARKER_API_BASE_URL}
									/>
								</Tooltip>
							</div>
							<div class="my-0.5 flex gap-2 pr-2">
								<SensitiveInput
									placeholder={$i18n.t('Enter Datalab Marker API Key')}
									required={false}
									bind:value={RAGConfig.DATALAB_MARKER_API_KEY}
								/>
							</div>

							<div class="flex flex-col gap-2 mt-2">
								<div class=" flex flex-col w-full justify-between">
									<div class=" mb-1 text-xs font-medium">
										{$i18n.t('Additional Config')}
									</div>
									<div class="flex w-full items-center relative">
										<Tooltip
											content={$i18n.t(
												'Additional configuration options for marker. This should be a JSON string with key-value pairs. For example, \'{"key": "value"}\'. Supported keys include: disable_links, keep_pageheader_in_output, keep_pagefooter_in_output, filter_blank_pages, drop_repeated_text, layout_coverage_threshold, merge_threshold, height_tolerance, gap_threshold, image_threshold, min_line_length, level_count, default_level'
											)}
											placement="top-start"
											className="w-full"
										>
											<Textarea
												bind:value={RAGConfig.DATALAB_MARKER_ADDITIONAL_CONFIG}
												placeholder={$i18n.t('Enter JSON config (e.g., {"disable_links": true})')}
											/>
										</Tooltip>
									</div>
								</div>
							</div>

							<div class="flex justify-between w-full mt-2">
								<div class="self-center text-xs font-medium">
									<Tooltip
										content={$i18n.t(
											'Significantly improves accuracy by using an LLM to enhance tables, forms, inline math, and layout detection. Will increase latency. Defaults to False.'
										)}
										placement="top-start"
									>
										{$i18n.t('Use LLM')}
									</Tooltip>
								</div>
								<div class="flex items-center">
									<Switch bind:state={RAGConfig.DATALAB_MARKER_USE_LLM} />
								</div>
							</div>
							<div class="flex justify-between w-full mt-2">
								<div class="self-center text-xs font-medium">
									<Tooltip
										content={$i18n.t('Skip the cache and re-run the inference. Defaults to False.')}
										placement="top-start"
									>
										{$i18n.t('Skip Cache')}
									</Tooltip>
								</div>
								<div class="flex items-center">
									<Switch bind:state={RAGConfig.DATALAB_MARKER_SKIP_CACHE} />
								</div>
							</div>
							<div class="flex justify-between w-full mt-2">
								<div class="self-center text-xs font-medium">
									<Tooltip
										content={$i18n.t(
											'Force OCR on all pages of the PDF. This can lead to worse results if you have good text in your PDFs. Defaults to False.'
										)}
										placement="top-start"
									>
										{$i18n.t('Force OCR')}
									</Tooltip>
								</div>
								<div class="flex items-center">
									<Switch bind:state={RAGConfig.DATALAB_MARKER_FORCE_OCR} />
								</div>
							</div>
							<div class="flex justify-between w-full mt-2">
								<div class="self-center text-xs font-medium">
									<Tooltip
										content={$i18n.t(
											'Whether to paginate the output. Each page will be separated by a horizontal rule and page number. Defaults to False.'
										)}
										placement="top-start"
									>
										{$i18n.t('Paginate')}
									</Tooltip>
								</div>
								<div class="flex items-center">
									<Switch bind:state={RAGConfig.DATALAB_MARKER_PAGINATE} />
								</div>
							</div>
							<div class="flex justify-between w-full mt-2">
								<div class="self-center text-xs font-medium">
									<Tooltip
										content={$i18n.t(
											'Strip existing OCR text from the PDF and re-run OCR. Ignored if Force OCR is enabled. Defaults to False.'
										)}
										placement="top-start"
									>
										{$i18n.t('Strip Existing OCR')}
									</Tooltip>
								</div>
								<div class="flex items-center">
									<Switch bind:state={RAGConfig.DATALAB_MARKER_STRIP_EXISTING_OCR} />
								</div>
							</div>
							<div class="flex justify-between w-full mt-2">
								<div class="self-center text-xs font-medium">
									<Tooltip
										content={$i18n.t(
											'Disable image extraction from the PDF. If Use LLM is enabled, images will be automatically captioned. Defaults to False.'
										)}
										placement="top-start"
									>
										{$i18n.t('Disable Image Extraction')}
									</Tooltip>
								</div>
								<div class="flex items-center">
									<Switch bind:state={RAGConfig.DATALAB_MARKER_DISABLE_IMAGE_EXTRACTION} />
								</div>
							</div>
							<div class="flex justify-between w-full mt-2">
								<div class="self-center text-xs font-medium">
									<Tooltip
										content={$i18n.t(
											'Format the lines in the output. Defaults to False. If set to True, the lines will be formatted to detect inline math and styles.'
										)}
										placement="top-start"
									>
										{$i18n.t('Format Lines')}
									</Tooltip>
								</div>
								<div class="flex items-center">
									<Switch bind:state={RAGConfig.DATALAB_MARKER_FORMAT_LINES} />
								</div>
							</div>
							<div class="flex justify-between w-full mt-2">
								<div class="self-center text-xs font-medium">
									<Tooltip
										content={$i18n.t(
											"The output format for the text. Can be 'json', 'markdown', or 'html'. Defaults to 'markdown'."
										)}
										placement="top-start"
									>
										{$i18n.t('Output Format')}
									</Tooltip>
								</div>
								<div class="">
									<select
										class="w-fit pr-8 rounded-sm px-2 text-xs bg-transparent outline-hidden text-right"
										bind:value={RAGConfig.DATALAB_MARKER_OUTPUT_FORMAT}
									>
										<option value="markdown">{$i18n.t('Markdown')}</option>
										<option value="json">{$i18n.t('JSON')}</option>
										<option value="html">{$i18n.t('HTML')}</option>
									</select>
								</div>
							</div>
						{:else if RAGConfig.CONTENT_EXTRACTION_ENGINE === 'external'}
							<div class="my-0.5 flex gap-2 pr-2">
								<input
									class="flex-1 w-full text-sm bg-transparent outline-hidden"
									placeholder={$i18n.t('Enter External Document Loader URL')}
									bind:value={RAGConfig.EXTERNAL_DOCUMENT_LOADER_URL}
								/>
								<SensitiveInput
									placeholder={$i18n.t('Enter External Document Loader API Key')}
									required={false}
									bind:value={RAGConfig.EXTERNAL_DOCUMENT_LOADER_API_KEY}
								/>
							</div>
						{:else if RAGConfig.CONTENT_EXTRACTION_ENGINE === 'tika'}
							<div class="flex w-full mt-1">
								<div class="flex-1 mr-2">
									<input
										class="flex-1 w-full text-sm bg-transparent outline-hidden"
										placeholder={$i18n.t('Enter Tika Server URL')}
										bind:value={RAGConfig.TIKA_SERVER_URL}
									/>
								</div>
							</div>
						{:else if RAGConfig.CONTENT_EXTRACTION_ENGINE === 'docling'}
							<div class="my-0.5 flex gap-2 pr-2">
								<input
									class="flex-1 w-full text-sm bg-transparent outline-hidden"
									placeholder={$i18n.t('Enter Docling Server URL')}
									bind:value={RAGConfig.DOCLING_SERVER_URL}
								/>
								<SensitiveInput
									placeholder={$i18n.t('Enter Docling API Key')}
									bind:value={RAGConfig.DOCLING_API_KEY}
									required={false}
								/>
							</div>

							<div class="flex flex-col gap-2 mt-2">
								<div class=" flex flex-col w-full justify-between">
									<div class=" mb-1 text-xs font-medium">
										{$i18n.t('Parameters')}
									</div>
									<div class="flex w-full items-center relative">
										<Textarea
											bind:value={RAGConfig.DOCLING_PARAMS}
											placeholder={$i18n.t('Enter additional parameters in JSON format')}
											minSize={100}
										/>
									</div>
								</div>
							</div>
						{:else if RAGConfig.CONTENT_EXTRACTION_ENGINE === 'document_intelligence'}
							<div class="my-0.5 flex gap-2 pr-2">
								<input
									class="flex-1 w-full text-sm bg-transparent outline-hidden"
									placeholder={$i18n.t('Enter Document Intelligence Endpoint')}
									bind:value={RAGConfig.DOCUMENT_INTELLIGENCE_ENDPOINT}
								/>
								<SensitiveInput
									placeholder={$i18n.t('Enter Document Intelligence Key')}
									bind:value={RAGConfig.DOCUMENT_INTELLIGENCE_KEY}
									required={false}
								/>
							</div>
							<div class="my-0.5 flex flex-col w-full">
								<div class=" mb-1 text-xs font-medium">
									{$i18n.t('Document Intelligence Model')}
								</div>
								<div class="flex w-full">
									<div class="flex-1 mr-2">
										<input
											class="flex-1 w-full text-sm bg-transparent outline-hidden"
											placeholder={$i18n.t('Enter Document Intelligence Model')}
											bind:value={RAGConfig.DOCUMENT_INTELLIGENCE_MODEL}
										/>
									</div>
								</div>
							</div>
						{:else if RAGConfig.CONTENT_EXTRACTION_ENGINE === 'mistral_ocr'}
							<div class="my-0.5 flex gap-2 pr-2">
								<input
									class="flex-1 w-full text-sm bg-transparent outline-hidden"
									placeholder={$i18n.t('Enter Mistral API Base URL')}
									bind:value={RAGConfig.MISTRAL_OCR_API_BASE_URL}
								/>
								<SensitiveInput
									placeholder={$i18n.t('Enter Mistral API Key')}
									bind:value={RAGConfig.MISTRAL_OCR_API_KEY}
								/>
							</div>
						{:else if RAGConfig.CONTENT_EXTRACTION_ENGINE === 'mineru'}
							<!-- API Mode Selection -->
							<div class="flex w-full mt-2">
								<div class="flex-1 flex justify-between">
									<div class="self-center text-xs font-medium">
										{$i18n.t('API Mode')}
									</div>
									<select
										class="w-fit pr-8 rounded-sm px-2 text-xs bg-transparent outline-hidden"
										bind:value={RAGConfig.MINERU_API_MODE}
										on:change={() => {
											// Auto-update URL when switching modes if it's empty or matches the opposite mode's default
											const cloudUrl = 'https://mineru.net/api/v4';
											const localUrl = 'http://localhost:8000';

											if (RAGConfig.MINERU_API_MODE === 'cloud') {
												if (!RAGConfig.MINERU_API_URL || RAGConfig.MINERU_API_URL === localUrl) {
													RAGConfig.MINERU_API_URL = cloudUrl;
												}
											} else {
												if (!RAGConfig.MINERU_API_URL || RAGConfig.MINERU_API_URL === cloudUrl) {
													RAGConfig.MINERU_API_URL = localUrl;
												}
											}
										}}
									>
										<option value="local">{$i18n.t('local')}</option>
										<option value="cloud">{$i18n.t('cloud')}</option>
									</select>
								</div>
							</div>

							<!-- API URL -->
							<div class="flex w-full mt-2">
								<input
									class="flex-1 w-full text-sm bg-transparent outline-hidden"
									placeholder={RAGConfig.MINERU_API_MODE === 'cloud'
										? $i18n.t('https://mineru.net/api/v4')
										: $i18n.t('http://localhost:8000')}
									bind:value={RAGConfig.MINERU_API_URL}
								/>
							</div>

							<div class="flex w-full mt-2">
								<SensitiveInput
									placeholder={$i18n.t('Enter MinerU API Key')}
									bind:value={RAGConfig.MINERU_API_KEY}
								/>
							</div>

							<div class="flex w-full mt-2">
								<div class="flex-1 flex justify-between">
									<div class="self-center text-xs font-medium">
										{$i18n.t('API Timeout')}
									</div>
									<input
										class="w-16 text-sm bg-transparent outline-hidden text-right"
										type="number"
										min="1"
										bind:value={RAGConfig.MINERU_API_TIMEOUT}
										placeholder="60"
									/>
								</div>
							</div>

							<!-- Parameters -->
							<div class="flex flex-col justify-between w-full mt-2">
								<div class="text-xs font-medium">
									<Tooltip
										content={$i18n.t(
											'Advanced parameters for MinerU parsing (enable_ocr, enable_formula, enable_table, language, model_version, page_ranges)'
										)}
										placement="top-start"
									>
										{$i18n.t('Parameters')}
									</Tooltip>
								</div>
								<div class="mt-1.5">
									<Textarea
										bind:value={RAGConfig.MINERU_PARAMS}
										placeholder={`{\n  "enable_ocr": false,\n  "enable_formula": true,\n  "enable_table": true,\n  "language": "en",\n  "model_version": "pipeline",\n  "page_ranges": ""\n}`}
										minSize={100}
									/>
								</div>
							</div>
						{/if}
					</div>
					{/if}

					<!-- 注释掉：Bypass Embedding and Retrieval、Text Splitter、Markdown Header Text Splitter -->
					{#if false}
					<div class="  mb-2.5 flex w-full justify-between">
						<div class=" self-center text-xs font-medium">
							<Tooltip content={$i18n.t('Full Context Mode')} placement="top-start">
								{$i18n.t('Bypass Embedding and Retrieval')}
							</Tooltip>
						</div>
						<div class="flex items-center relative">
							<Switch bind:state={RAGConfig.BYPASS_EMBEDDING_AND_RETRIEVAL} />
						</div>
					</div>

					<div class="  mb-2.5 flex w-full justify-between">
						<div class=" self-center text-xs font-medium">{$i18n.t('Text Splitter')}</div>
						<div class="flex items-center relative">
							<select
								class="w-fit pr-8 rounded-sm px-2 text-xs bg-transparent outline-hidden text-right"
								bind:value={RAGConfig.TEXT_SPLITTER}
							>
								<option value="">{$i18n.t('Default')} ({$i18n.t('Character')})</option>
								<option value="token">{$i18n.t('Token')} ({$i18n.t('Tiktoken')})</option>
							</select>
						</div>
					</div>

					<div class="  mb-2.5 flex w-full justify-between">
						<div class=" self-center text-xs font-medium">
							{$i18n.t('Markdown Header Text Splitter')}
						</div>
						<div class="flex items-center relative">
							<Switch bind:state={RAGConfig.ENABLE_MARKDOWN_HEADER_TEXT_SPLITTER} />
						</div>
					</div>
					{/if}

				<div
					class="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3.5 mt-2"
				>
					<div class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2.5">
						{$i18n.t('Chunk Parameters')}
					</div>
					<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('Chunk Size')}
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								type="number"
								placeholder={$i18n.t('Enter Chunk Size')}
								bind:value={RAGConfig.CHUNK_SIZE}
								autocomplete="off"
								min="0"
							/>
						</div>

						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('Chunk Overlap')}
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								type="number"
								placeholder={$i18n.t('Enter Chunk Overlap')}
								bind:value={RAGConfig.CHUNK_OVERLAP}
								autocomplete="off"
								min="0"
							/>
						</div>

						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								<Tooltip
									placement="top-start"
									content={$i18n.t(
										'Chunks smaller than this threshold will be merged with neighboring chunks when possible. Set to 0 to disable merging.'
									)}
								>
									{$i18n.t('Chunk Min Size Target')}
								</Tooltip>
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								type="number"
								placeholder={$i18n.t('Enter Chunk Min Size Target')}
								bind:value={RAGConfig.CHUNK_MIN_SIZE_TARGET}
								autocomplete="off"
								min="0"
							/>
						</div>
					</div>
				</div>
			</div>

			{/if}

			<!-- Embedding -->
			<div>
				<div class="flex items-center justify-between mt-0.5 mb-2 gap-2 pr-0.5">
					<div class="text-base font-medium shrink-0">{$i18n.t('Embedding')}</div>

					<Tooltip
						content={$i18n.t(
							'These settings are shared across all users in this workspace.'
						)}
						className="inline-flex items-center gap-1.5 text-xs leading-5 text-gray-400 dark:text-gray-500 cursor-help whitespace-nowrap"
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 20 20"
							fill="currentColor"
							class="size-3.5 shrink-0"
							aria-hidden="true"
						>
							<path
								fill-rule="evenodd"
								d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Zm-7-4a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM9 9a.75.75 0 0 0 0 1.5h.253a.25.25 0 0 1 .244.304l-.459 2.066A1.75 1.75 0 0 0 10.747 15H11a.75.75 0 0 0 0-1.5h-.253a.25.25 0 0 1-.244-.304l.459-2.066A1.75 1.75 0 0 0 9.253 9H9Z"
								clip-rule="evenodd"
							/>
						</svg>
						<span>{$i18n.t('Shared with all users')}</span>
					</Tooltip>
				</div>
				<hr class="border-gray-100/30 dark:border-gray-850/30 mb-3" />

				<!-- Chunking (title inside the box) -->
				<div class="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3.5">
					<div class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
						{$i18n.t('Chunking')}
					</div>
					<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('Chunk Size')}
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								type="number"
								placeholder={$i18n.t('Enter Chunk Size')}
								bind:value={RAGConfig.CHUNK_SIZE}
								autocomplete="off"
								min="0"
							/>
						</div>

						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('Chunk Overlap')}
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								type="number"
								placeholder={$i18n.t('Enter Chunk Overlap')}
								bind:value={RAGConfig.CHUNK_OVERLAP}
								autocomplete="off"
								min="0"
							/>
						</div>

						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								<Tooltip
									placement="top-start"
									content={$i18n.t(
										'Chunks smaller than this threshold will be merged with neighboring chunks when possible. Set to 0 to disable merging.'
									)}
								>
									{$i18n.t('Chunk Min Size Target')}
								</Tooltip>
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								type="number"
								placeholder={$i18n.t('Enter Chunk Min Size Target')}
								bind:value={RAGConfig.CHUNK_MIN_SIZE_TARGET}
								autocomplete="off"
								min="0"
							/>
						</div>
					</div>
				</div>

				<!-- Embedding endpoint, API & model (combined) -->
				<div class="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3.5 mt-2">
					<div class="flex items-center justify-between mb-3">
						<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
							{$i18n.t('Embedding Model')}
						</div>
						<Tooltip content={$i18n.t('Verify')}>
							<button
								class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 transition disabled:opacity-50 disabled:cursor-not-allowed"
								type="button"
								on:click={verifyEmbeddingHandler}
								disabled={verifyingEmbedding || !OpenAIUrl}
							>
								{#if verifyingEmbedding}
									<Spinner className="size-3.5" />
								{:else}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										aria-hidden="true"
										class="size-3.5"
									>
										<path
											fill-rule="evenodd"
											d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
											clip-rule="evenodd"
										/>
									</svg>
								{/if}
								<span>{$i18n.t('Verify')}</span>
							</button>
						</Tooltip>
					</div>
					<div class="flex flex-col gap-3">
						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('API Base URL')}
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								placeholder={$i18n.t('API Base URL')}
								bind:value={OpenAIUrl}
							/>
						</div>
						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('API Key')}
							</label>
							<div
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:bg-gray-850 flex items-center"
							>
								<SensitiveInput
									placeholder={$i18n.t('API Key')}
									bind:value={OpenAIKey}
									required={false}
									outerClassName="flex flex-1 bg-transparent items-center"
									inputClassName="w-full text-sm bg-transparent dark:text-gray-300 outline-hidden"
									showButtonClassName="pl-1.5 text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200 transition bg-transparent"
								/>
							</div>
						</div>
						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('Embedding Model')}
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								placeholder={$i18n.t('Set embedding model (e.g. {{model}})', {
									model: RAG_EMBEDDING_MODEL.slice(-40)
								})}
								bind:value={RAG_EMBEDDING_MODEL}
							/>
						</div>
					</div>
				</div>

				<!-- Performance options -->
				<div class="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3.5 mt-2">
					<div class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
						{$i18n.t('Performance')}
					</div>
					<div class="divide-y divide-gray-100 dark:divide-gray-800">
						<div class="flex items-center justify-between py-2.5">
							<div class="text-xs font-medium">
								{$i18n.t('Embedding Batch Size')}
							</div>
							<input
								bind:value={RAG_EMBEDDING_BATCH_SIZE}
								type="number"
								class="bg-gray-50 dark:bg-gray-850 dark:text-gray-300 rounded-lg py-1 px-2 text-center w-20 text-sm outline-none"
								min="-2"
								max="16000"
								step="1"
							/>
						</div>

						<div class="flex items-center justify-between py-2.5">
							<div class="text-xs font-medium">
								<Tooltip
									content={$i18n.t(
										'Runs embedding tasks concurrently to speed up processing. Turn off if rate limits become an issue.'
									)}
									placement="top-start"
								>
									{$i18n.t('Async Embedding Processing')}
								</Tooltip>
							</div>
							<Switch bind:state={ENABLE_ASYNC_EMBEDDING} />
						</div>

						<div class="flex items-center justify-between py-2.5">
							<div class="text-xs font-medium">
								<Tooltip
									content={$i18n.t(
										'Limits the number of concurrent embedding requests. Set to 0 for unlimited.'
									)}
									placement="top-start"
								>
									{$i18n.t('Embedding Concurrent Requests')}
								</Tooltip>
							</div>
							<input
								bind:value={RAG_EMBEDDING_CONCURRENT_REQUESTS}
								type="number"
								class="bg-gray-50 dark:bg-gray-850 dark:text-gray-300 rounded-lg py-1 px-2 text-center w-20 text-sm outline-none"
								min="0"
								step="1"
							/>
						</div>
					</div>
				</div>
			</div>

			<!-- Retrieval -->
			<div>
				<div class="text-base font-medium mt-0.5 mb-2">{$i18n.t('Retrieval')}</div>
				<hr class="border-gray-100/30 dark:border-gray-850/30 mb-3" />

				<!-- Reranker endpoint, API & model (combined) -->
				<div class="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3.5">
					<div class="flex items-center justify-between mb-3">
						<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
							{$i18n.t('Reranking Model')}
						</div>
						<Tooltip content={$i18n.t('Verify')}>
							<button
								class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 transition disabled:opacity-50 disabled:cursor-not-allowed"
								type="button"
								on:click={verifyRerankerHandler}
								disabled={verifyingReranker || !RAGConfig?.RAG_EXTERNAL_RERANKER_URL}
							>
								{#if verifyingReranker}
									<Spinner className="size-3.5" />
								{:else}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										aria-hidden="true"
										class="size-3.5"
									>
										<path
											fill-rule="evenodd"
											d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
											clip-rule="evenodd"
										/>
									</svg>
								{/if}
								<span>{$i18n.t('Verify')}</span>
							</button>
						</Tooltip>
					</div>
					<div class="flex flex-col gap-3">
						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('API Base URL')}
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								placeholder={$i18n.t('API Base URL')}
								bind:value={RAGConfig.RAG_EXTERNAL_RERANKER_URL}
							/>
						</div>
						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('API Key')}
							</label>
							<div
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:bg-gray-850 flex items-center"
							>
								<SensitiveInput
									placeholder={$i18n.t('API Key')}
									bind:value={RAGConfig.RAG_EXTERNAL_RERANKER_API_KEY}
									required={false}
									outerClassName="flex flex-1 bg-transparent items-center"
									inputClassName="w-full text-sm bg-transparent dark:text-gray-300 outline-hidden"
									showButtonClassName="pl-1.5 text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200 transition bg-transparent"
								/>
							</div>
						</div>
						<div class="flex flex-col">
							<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
								{$i18n.t('Reranking Model')}
							</label>
							<input
								class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
								placeholder={$i18n.t('Set reranking model (e.g. {{model}})', {
									model: 'BAAI/bge-reranker-v2-m3'
								})}
								bind:value={RAGConfig.RAG_RERANKING_MODEL}
							/>
						</div>
					</div>
				</div>

				<!-- Search params -->
				<div class="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3.5 mt-2">
					<div class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
						{$i18n.t('Search Parameters')}
					</div>
					<div class="divide-y divide-gray-100 dark:divide-gray-800">
						<div class="flex items-center justify-between py-2.5">
							<div class="text-xs font-medium">{$i18n.t('Top K')}</div>
							<input
								class="bg-gray-50 dark:bg-gray-850 dark:text-gray-300 rounded-lg py-1 px-2 text-center w-20 text-sm outline-none"
								type="number"
								bind:value={RAGConfig.TOP_K}
								autocomplete="off"
								min="0"
							/>
						</div>

						<div class="flex items-center justify-between py-2.5">
							<div class="text-xs font-medium">{$i18n.t('Top K Reranker')}</div>
							<input
								class="bg-gray-50 dark:bg-gray-850 dark:text-gray-300 rounded-lg py-1 px-2 text-center w-20 text-sm outline-none"
								type="number"
								bind:value={RAGConfig.TOP_K_RERANKER}
								autocomplete="off"
								min="0"
							/>
						</div>

						<div class="flex items-center justify-between py-2.5">
							<div class="text-xs font-medium">{$i18n.t('Reranking Batch Size')}</div>
							<input
								class="bg-gray-50 dark:bg-gray-850 dark:text-gray-300 rounded-lg py-1 px-2 text-center w-20 text-sm outline-none"
								type="number"
								bind:value={RAGConfig.RAG_RERANKING_BATCH_SIZE}
								autocomplete="off"
								min="1"
								max="16000"
								step="1"
							/>
						</div>

						<div class="flex items-center justify-between py-2.5">
							<div class="text-xs font-medium">
								<Tooltip
									content={$i18n.t(
										'Note: If you set a minimum score, the search will only return documents with a score greater than or equal to the minimum score.'
									)}
									placement="top-start"
								>
									{$i18n.t('Relevance Threshold')}
								</Tooltip>
							</div>
							<input
								class="bg-gray-50 dark:bg-gray-850 dark:text-gray-300 rounded-lg py-1 px-2 text-center w-20 text-sm outline-none"
								type="number"
								step="0.01"
								bind:value={RAGConfig.RELEVANCE_THRESHOLD}
								autocomplete="off"
								min="0.0"
								title={$i18n.t('The score should be a value between 0.0 (0%) and 1.0 (100%).')}
							/>
						</div>

						<!-- BM25 Weight -->
						<div class="py-2.5">
							<div class="flex items-center justify-between">
								<div class="text-xs font-medium">
									<Tooltip
										content={$i18n.t(
											'The Weight of BM25 Hybrid Search. 0 more semantic, 1 more lexical. Default 0.5'
										)}
										placement="top-start"
									>
										{$i18n.t('BM25 Weight')}
									</Tooltip>
								</div>
								<button
									class="text-xs px-2 py-0.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-850 transition outline-hidden text-gray-500 dark:text-gray-400"
									type="button"
									on:click={() => {
										RAGConfig.HYBRID_BM25_WEIGHT =
											(RAGConfig?.HYBRID_BM25_WEIGHT ?? null) === null ? 0.5 : null;
									}}
								>
									{(RAGConfig?.HYBRID_BM25_WEIGHT ?? null) === null
										? $i18n.t('Default')
										: $i18n.t('Custom')}
								</button>
							</div>

							{#if (RAGConfig?.HYBRID_BM25_WEIGHT ?? null) !== null}
								<div class="flex mt-2 gap-2 items-center">
									<div class="flex-1">
										<input
											id="steps-range"
											type="range"
											min="0"
											max="1"
											step="0.05"
											bind:value={RAGConfig.HYBRID_BM25_WEIGHT}
											class="w-full h-1.5 rounded-lg appearance-none cursor-pointer bg-gray-100 dark:bg-gray-800"
										/>
										<div
											class="flex justify-between mt-0.5 text-[10px] text-gray-400 dark:text-gray-500"
										>
											<span>{$i18n.t('semantic')}</span>
											<span>{$i18n.t('lexical')}</span>
										</div>
									</div>
									<input
										bind:value={RAGConfig.HYBRID_BM25_WEIGHT}
										type="number"
										class="bg-gray-50 dark:bg-gray-850 dark:text-gray-300 rounded-lg py-1 px-2 text-center w-16 text-sm outline-none"
										min="0"
										max="1"
										step="any"
									/>
								</div>
							{/if}
						</div>
					</div>
				</div>

				<!-- RAG Template -->
				<div class="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3.5 mt-2">
					<div class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
						{$i18n.t('RAG Template')}
					</div>
					<Tooltip
						content={$i18n.t(
							'Leave empty to use the default prompt, or enter a custom prompt'
						)}
						placement="top-start"
						className="w-full"
					>
						<Textarea
							bind:value={RAGConfig.RAG_TEMPLATE}
							placeholder={$i18n.t(
								'Leave empty to use the default prompt, or enter a custom prompt'
							)}
						/>
					</Tooltip>
				</div>
			</div>

			<!-- Document Preprocessing (meteokb) -->
			<div class="mb-3">
				<div class="text-base font-medium mt-0.5 mb-2">
					{$i18n.t('Document Preprocessing')}
				</div>

				<div class="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3.5">
					<div class="flex items-center justify-between mb-3">
						<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
							{$i18n.t('Preprocessing Service URL')}
						</div>
						<Tooltip content={$i18n.t('Verify')}>
							<button
								class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 transition disabled:opacity-50 disabled:cursor-not-allowed"
								type="button"
								on:click={verifyPreprocessServiceHandler}
								disabled={verifyingPreprocessService || !RAGConfig.DOC_PREPROCESS_SERVICE_URL}
							>
								{#if verifyingPreprocessService}
									<Spinner className="size-3.5" />
								{:else}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										aria-hidden="true"
										class="size-3.5"
									>
										<path
											fill-rule="evenodd"
											d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
											clip-rule="evenodd"
										/>
									</svg>
								{/if}
								<span>{$i18n.t('Verify')}</span>
							</button>
						</Tooltip>
					</div>
					<div class="flex flex-col">
						<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
							{$i18n.t('API Base URL')}
						</label>
						<input
							class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
							bind:value={RAGConfig.DOC_PREPROCESS_SERVICE_URL}
							placeholder="http://localhost:8100"
						/>
					</div>
				</div>

				<div class="rounded-xl border border-gray-100 dark:border-gray-800 px-4 py-3.5 mt-2">
					<div class="flex items-center justify-between mb-3">
						<div class="text-sm font-medium text-gray-700 dark:text-gray-300">
							{$i18n.t('Metadata Extraction (LLM)')}
						</div>
						<div class="flex items-center gap-2">
							{#if RAGConfig.DOC_PREPROCESS_ENRICH_ENABLED}
								<Tooltip content={$i18n.t('Verify')}>
									<button
										class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 transition disabled:opacity-50 disabled:cursor-not-allowed"
										type="button"
										on:click={verifyEnrichHandler}
										disabled={verifyingEnrich || !RAGConfig.DOC_PREPROCESS_ENRICH_BASE_URL}
									>
										{#if verifyingEnrich}
											<Spinner className="size-3.5" />
										{:else}
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 20 20"
												fill="currentColor"
												aria-hidden="true"
												class="size-3.5"
											>
												<path
													fill-rule="evenodd"
													d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
													clip-rule="evenodd"
												/>
											</svg>
										{/if}
										<span>{$i18n.t('Verify')}</span>
									</button>
								</Tooltip>
							{/if}
							<Switch bind:state={RAGConfig.DOC_PREPROCESS_ENRICH_ENABLED} />
						</div>
					</div>

					{#if RAGConfig.DOC_PREPROCESS_ENRICH_ENABLED}
						<div class="flex flex-col gap-3">
							<div class="flex flex-col">
								<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
									{$i18n.t('API Base URL')}
								</label>
								<input
									class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
									bind:value={RAGConfig.DOC_PREPROCESS_ENRICH_BASE_URL}
									placeholder="https://api.openai.com/v1"
								/>
							</div>
							<div class="flex flex-col">
								<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
									{$i18n.t('API Key')}
								</label>
								<div
									class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:bg-gray-850 flex items-center"
								>
									<SensitiveInput
										placeholder={$i18n.t('API Key')}
										bind:value={RAGConfig.DOC_PREPROCESS_ENRICH_API_KEY}
										required={false}
										outerClassName="flex flex-1 bg-transparent items-center"
										inputClassName="w-full text-sm bg-transparent dark:text-gray-300 outline-hidden"
										showButtonClassName="pl-1.5 text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200 transition bg-transparent"
									/>
								</div>
							</div>
							<div class="flex flex-col">
								<label class="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5">
									{$i18n.t('Model')}
								</label>
								<input
									class="w-full rounded-lg py-1.5 px-3 text-sm bg-gray-50 dark:text-gray-300 dark:bg-gray-850 outline-hidden"
									bind:value={RAGConfig.DOC_PREPROCESS_ENRICH_MODEL}
									placeholder={$i18n.t('Set model name')}
								/>
							</div>
						</div>
					{/if}
				</div>
			</div>

				<!-- 注释掉：集成（Integration）部分（Google Drive、OneDrive），暂不考虑此功能 -->
				{#if false}
				<div class="mb-3">
					<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Integration')}</div>

					<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div class="  mb-2.5 flex w-full justify-between">
						<div class=" self-center text-xs font-medium">{$i18n.t('Google Drive')}</div>
						<div class="flex items-center relative">
							<Switch bind:state={RAGConfig.ENABLE_GOOGLE_DRIVE_INTEGRATION} />
						</div>
					</div>

					<div class="  mb-2.5 flex w-full justify-between">
						<div class=" self-center text-xs font-medium">{$i18n.t('OneDrive')}</div>
						<div class="flex items-center relative">
							<Switch bind:state={RAGConfig.ENABLE_ONEDRIVE_INTEGRATION} />
						</div>
					</div>
				</div>
				{/if}

				<!-- 注释掉：危险区域（Danger Zone）部分（重置上传目录、重置向量库、重建索引），暂不考虑此功能 -->
				{#if false}
				<div class="mb-3">
					<div class=" mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Danger Zone')}</div>

					<hr class=" border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div class="  mb-2.5 flex w-full justify-between">
						<div class=" self-center text-xs font-medium">{$i18n.t('Reset Upload Directory')}</div>
						<div class="flex items-center relative">
							<button
								class="text-xs"
								type="button"
								on:click={() => {
									showResetUploadDirConfirm = true;
								}}
							>
								{$i18n.t('Reset')}
							</button>
						</div>
					</div>

					<div class="  mb-2.5 flex w-full justify-between">
						<div class=" self-center text-xs font-medium">
							{$i18n.t('Reset Vector Storage/Knowledge')}
						</div>
						<div class="flex items-center relative">
							<button
								class="text-xs"
								type="button"
								on:click={() => {
									showResetConfirm = true;
								}}
							>
								{$i18n.t('Reset')}
							</button>
						</div>
					</div>
					<div class="  mb-2.5 flex w-full justify-between">
						<div class=" self-center text-xs font-medium">
							{$i18n.t('Reindex Knowledge Base Vectors')}
						</div>
						<div class="flex items-center relative">
							<button
								class="text-xs"
								type="button"
								on:click={() => {
									showReindexConfirm = true;
								}}
							>
								{$i18n.t('Reindex')}
							</button>
						</div>
					</div>
				</div>
				{/if}
		</div>
		<div class="flex justify-end pt-3 text-sm font-medium">
			<button
				class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-lg"
				type="submit"
			>
				{$i18n.t('Save')}
			</button>
		</div>
	{:else}
		<div class="flex items-center justify-center h-full">
			<Spinner className="size-5" />
		</div>
	{/if}
</form>
