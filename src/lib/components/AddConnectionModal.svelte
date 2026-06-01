<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import { settings } from '$lib/stores';
	import { verifyOpenAIConnection } from '$lib/apis/openai';
	import { verifyOllamaConnection } from '$lib/apis/ollama';

	import Modal from '$lib/components/common/Modal.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	export let onSubmit: Function = () => {};
	export let onDelete: Function = () => {};

	export let show = false;
	export let edit = false;

	export let ollama = false;
	export let direct = false;

	export let connection = null;

	let url = '';
	let key = '';

	let loading = false;
	let verifying = false;

	/* ---- kept for backward compat in config payload ---- */
	let auth_type = 'bearer';
	let connectionType = 'external';
	let enable = true;
	let prefixId = '';
	let tags = [];
	let modelIds = [];
	let headers = '';
	let azure = false;
	let apiVersion = '';
	let apiType = '';

	const CONNECTION_ERROR_PATTERNS: Array<{ test: RegExp; key: string }> = [
		{
			test: /didn't provide an API key|provide your API key in an Authorization header/i,
			key: 'You need to provide your API key in an Authorization header using Bearer auth.'
		},
		{
			test: /missing bearer authentication/i,
			key: 'Missing bearer authentication in header'
		},
		{
			test: /incorrect API key provided/i,
			key: 'Incorrect API key provided'
		},
		{
			test: /invalid[_\s-]?api[_\s-]?key|invalid authentication/i,
			key: 'Invalid API key'
		},
		{
			test: /you exceeded your current quota|insufficient[_\s-]?quota/i,
			key: 'You exceeded your current quota, please check your plan and billing details.'
		},
		{
			test: /rate limit/i,
			key: 'Rate limit exceeded, please try again later.'
		},
		{
			test: /the model.*does not exist|model[_\s-]?not[_\s-]?found/i,
			key: 'The requested model does not exist or you do not have access to it.'
		},
		{
			test: /context length|maximum context length/i,
			key: 'The request exceeds the maximum context length of the model.'
		},
		{
			test: /server (?:is )?overloaded|service unavailable/i,
			key: 'The server is overloaded, please try again later.'
		},
		{
			test: /connection (?:refused|reset|timed? ?out)|failed to connect|ECONNREFUSED|ETIMEDOUT/i,
			key: 'Failed to connect to the server, please check the URL and network.'
		},
		{
			test: /not found|404/i,
			key: 'Endpoint not found (404). Please check the URL.'
		},
		{
			test: /unauthorized|401/i,
			key: 'Unauthorized (401). Please check your API key.'
		},
		{
			test: /forbidden|403/i,
			key: 'Forbidden (403). You do not have permission to access this resource.'
		},
		{
			test: /internal server error|500/i,
			key: 'Internal server error (500).'
		},
		{
			test: /bad gateway|502/i,
			key: 'Bad gateway (502).'
		},
		{
			test: /gateway timeout|504/i,
			key: 'Gateway timeout (504).'
		},
		{
			test: /network/i,
			key: 'Network Problem'
		}
	];

	const translateMessage = (message: string): string => {
		const trimmed = message.trim();
		if (!trimmed) {
			return $i18n.t('Network Problem');
		}
		const direct = $i18n.t(trimmed);
		if (direct !== trimmed) {
			return direct;
		}
		for (const { test, key } of CONNECTION_ERROR_PATTERNS) {
			if (test.test(trimmed)) {
				return $i18n.t(key);
			}
		}
		return trimmed;
	};

	const translateConnectionError = (error: unknown): string => {
		const raw = `${error ?? ''}`;
		const match = raw.match(/^(OpenAI|Ollama):\s*([\s\S]*)$/);
		if (match) {
			return `${match[1]}: ${translateMessage(match[2])}`;
		}
		return translateMessage(raw);
	};

	const verifyOllamaHandler = async () => {
		url = url.replace(/\/$/, '');
		const res = await verifyOllamaConnection(localStorage.token, { url, key }).catch((error) => {
			toast.error(translateConnectionError(error));
		});
		if (res) {
			toast.success($i18n.t('Server connection verified'));
		}
	};

	const verifyOpenAIHandler = async () => {
		url = url.replace(/\/$/, '');
		const res = await verifyOpenAIConnection(
			localStorage.token,
			{ url, key, config: { auth_type } },
			direct
		).catch((error) => {
			toast.error(translateConnectionError(error));
		});
		if (res) {
			toast.success($i18n.t('Server connection verified'));
		}
	};

	const verifyHandler = async () => {
		verifying = true;
		if (ollama) {
			await verifyOllamaHandler();
		} else {
			await verifyOpenAIHandler();
		}
		verifying = false;
	};

	const submitHandler = async () => {
		loading = true;

		if (!ollama && !url) {
			loading = false;
			toast.error($i18n.t('URL is required'));
			return;
		}

		url = url.replace(/\/$/, '');

		const conn = {
			url,
			key,
			config: {
				enable,
				tags,
				prefix_id: prefixId,
				model_ids: modelIds,
				connection_type: connectionType,
				auth_type,
				...(headers ? { headers: JSON.parse(headers) } : {}),
				...(azure ? { azure: true, api_version: apiVersion } : {}),
				...(apiType ? { api_type: apiType } : {})
			}
		};

		await onSubmit(conn);

		loading = false;
		show = false;

		url = '';
		key = '';
	};

	const init = () => {
		if (connection) {
			url = connection.url;
			key = connection.key;
			auth_type = connection.config?.auth_type ?? 'bearer';
			headers = connection.config?.headers ? JSON.stringify(connection.config.headers, null, 2) : '';
			enable = connection.config?.enable ?? true;
			tags = connection.config?.tags ?? [];
			prefixId = connection.config?.prefix_id ?? '';
			modelIds = connection.config?.model_ids ?? [];
			connectionType = connection.config?.connection_type ?? 'external';
			azure = connection.config?.azure ?? false;
			apiVersion = connection.config?.api_version ?? '';
			apiType = connection.config?.api_type ?? '';
		}
	};

	$: if (show) {
		init();
	}

	onMount(() => {
		init();
	});
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between items-center px-6 pt-5 pb-4">
			<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">
				{#if edit}
					{$i18n.t('Edit Connection')}
				{:else}
					{$i18n.t('Add Connection')}
				{/if}
			</div>
			<button
				class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
				aria-label={$i18n.t('Close')}
				on:click={() => {
					show = false;
				}}
				type="button"
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="px-6 pb-6 dark:text-gray-200">
			<form class="flex flex-col w-full space-y-3" on:submit|preventDefault={submitHandler}>
				<!-- URL field -->
				<div class="flex flex-col w-full">
					<label
						for="url-input"
						class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
					>
						{$i18n.t('URL')}
					</label>

					<div
						class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
					>
						<input
							id="url-input"
							class="flex-1 min-w-0 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
							type="text"
							bind:value={url}
							placeholder={$i18n.t('API Base URL')}
							autocomplete="off"
							required
						/>

						<Tooltip content={$i18n.t('Verify Connection')}>
							<button
								class="shrink-0 p-1 rounded-md text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200 transition disabled:opacity-50 disabled:cursor-not-allowed"
								on:click={verifyHandler}
								type="button"
								aria-label={$i18n.t('Verify Connection')}
								disabled={verifying || !url}
							>
								{#if verifying}
									<Spinner className="size-4" />
								{:else}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										aria-hidden="true"
										class="size-4"
									>
										<path
											fill-rule="evenodd"
											d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
											clip-rule="evenodd"
										/>
									</svg>
								{/if}
							</button>
						</Tooltip>
					</div>

					<p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t('Example: https://api.example.com/v1')}
					</p>
				</div>

				<!-- API Key field -->
				<div class="flex flex-col w-full">
					<label
						for="key-input"
						class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
					>
						{$i18n.t('API Key')}
					</label>

					<div
						class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
					>
						<SensitiveInput
							id="key-input"
							bind:value={key}
							placeholder={$i18n.t('Paste your API key')}
							required={false}
							outerClassName="flex flex-1 bg-transparent items-center"
							inputClassName="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
							showButtonClassName="pl-1.5 text-gray-400 hover:text-gray-700 dark:text-gray-500 dark:hover:text-gray-200 transition bg-transparent"
						/>
					</div>

					<p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t('Optional. Leave empty if the endpoint does not require authentication.')}
					</p>
				</div>

				{#if !ollama}
					<!-- Model IDs (whitelist) field -->
					<div class="flex flex-col w-full">
						<label
							for="model-ids-input"
							class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide"
						>
							{$i18n.t('Model IDs')}
						</label>

						<div
							class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all"
						>
							<input
								id="model-ids-input"
								class="flex-1 min-w-0 text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
								type="text"
								value={modelIds.join(', ')}
								on:input={(e) => {
									const raw = (e.currentTarget as HTMLInputElement).value;
									modelIds = raw
										.split(',')
										.map((s) => s.trim())
										.filter((s) => s.length > 0);
								}}
								placeholder={$i18n.t('e.g. qwen36, gpt-4o (comma-separated)')}
								autocomplete="off"
							/>
						</div>

						<p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t(
								'Optional. Whitelist of model IDs to expose from this connection. Leave empty to show all models.'
							)}
						</p>
					</div>
				{/if}

				<!-- Footer actions -->
				<div
					class="flex items-center justify-between gap-2 pt-3 mt-2 border-t border-gray-100 dark:border-gray-800"
				>
					<div>
						{#if edit}
							<button
								class="px-3 py-1.5 text-sm font-medium rounded-lg text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 transition-colors"
								type="button"
								on:click={() => {
									onDelete();
									show = false;
								}}
							>
								{$i18n.t('Delete')}
							</button>
						{/if}
					</div>

					<div class="flex items-center gap-2">
						<button
							class="px-3 py-1.5 text-sm font-medium rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
							type="button"
							on:click={() => {
								show = false;
							}}
						>
							{$i18n.t('Cancel')}
						</button>

						<button
							class="px-5 py-1.5 text-sm font-medium bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 transition-all rounded-lg shadow-sm flex items-center gap-2 {loading
								? ' cursor-not-allowed opacity-70'
								: ''}"
							type="submit"
							disabled={loading}
						>
							{$i18n.t('Save')}

							{#if loading}
								<Spinner className="size-3.5" />
							{/if}
						</button>
					</div>
				</div>
			</form>
		</div>
	</div>
</Modal>
