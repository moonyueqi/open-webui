<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, onMount, getContext, tick } from 'svelte';

	const dispatch = createEventDispatcher();

	import { getOllamaConfig, updateOllamaConfig } from '$lib/apis/ollama';
	import { getOpenAIConfig, updateOpenAIConfig, getOpenAIModels } from '$lib/apis/openai';
	import { getModels as _getModels, getBackendConfig } from '$lib/apis';
	import { getConnectionsConfig, setConnectionsConfig } from '$lib/apis/configs';

	import { config, models, settings, user } from '$lib/stores';

	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import AddConnectionModal from '$lib/components/AddConnectionModal.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Cog6 from '$lib/components/icons/Cog6.svelte';

	const i18n = getContext('i18n');

	const getModels = async () => {
		const models = await _getModels(
			localStorage.token,
			$config?.features?.enable_direct_connections && ($settings?.directConnections ?? null),
			false,
			true
		);
		return models;
	};

	let OPENAI_API_KEYS = [''];
	let OPENAI_API_BASE_URLS = [''];
	let OPENAI_API_CONFIGS = {};

	let ENABLE_OPENAI_API: null | boolean = null;

	let OLLAMA_BASE_URLS = [''];
	let OLLAMA_API_CONFIGS = {};
	let ENABLE_OLLAMA_API: null | boolean = null;

	let connectionsConfig = null;
	let loaded = false;

	let showAddConnectionModal = false;
	let showEditConnectionModal = false;
	let editConnectionIdx = -1;

	let showDeleteConfirmDialog = false;
	let deleteConnectionIdx = -1;

	const updateOpenAIHandler = async () => {
		if (ENABLE_OPENAI_API !== null) {
			OPENAI_API_BASE_URLS = OPENAI_API_BASE_URLS.map((url) => url.replace(/\/$/, ''));

			if (OPENAI_API_KEYS.length !== OPENAI_API_BASE_URLS.length) {
				if (OPENAI_API_KEYS.length > OPENAI_API_BASE_URLS.length) {
					OPENAI_API_KEYS = OPENAI_API_KEYS.slice(0, OPENAI_API_BASE_URLS.length);
				}
				if (OPENAI_API_KEYS.length < OPENAI_API_BASE_URLS.length) {
					const diff = OPENAI_API_BASE_URLS.length - OPENAI_API_KEYS.length;
					for (let i = 0; i < diff; i++) {
						OPENAI_API_KEYS.push('');
					}
				}
			}

			const res = await updateOpenAIConfig(localStorage.token, {
				ENABLE_OPENAI_API: ENABLE_OPENAI_API,
				OPENAI_API_BASE_URLS: OPENAI_API_BASE_URLS,
				OPENAI_API_KEYS: OPENAI_API_KEYS,
				OPENAI_API_CONFIGS: OPENAI_API_CONFIGS
			}).catch((error) => {
				toast.error(`${error}`);
			});

			if (res) {
				toast.success($i18n.t('OpenAI API settings updated'));
				await models.set(await getModels());
			}
		}
	};

	const addConnectionHandler = async (connection) => {
		OPENAI_API_BASE_URLS = [...OPENAI_API_BASE_URLS, connection.url];
		OPENAI_API_KEYS = [...OPENAI_API_KEYS, connection.key];
		OPENAI_API_CONFIGS[OPENAI_API_BASE_URLS.length - 1] = connection.config;

		await updateOpenAIHandler();
	};

	const editConnectionHandler = async (connection) => {
		if (editConnectionIdx >= 0) {
			OPENAI_API_BASE_URLS[editConnectionIdx] = connection.url;
			OPENAI_API_KEYS[editConnectionIdx] = connection.key;
			OPENAI_API_CONFIGS[editConnectionIdx] = connection.config;
			OPENAI_API_BASE_URLS = [...OPENAI_API_BASE_URLS];
			OPENAI_API_KEYS = [...OPENAI_API_KEYS];

			await updateOpenAIHandler();
		}
	};

	const deleteConnection = async (idx) => {
		OPENAI_API_BASE_URLS = OPENAI_API_BASE_URLS.filter((_, i) => i !== idx);
		OPENAI_API_KEYS = OPENAI_API_KEYS.filter((_, i) => i !== idx);

		let newConfig = {};
		OPENAI_API_BASE_URLS.forEach((_, newIdx) => {
			newConfig[newIdx] = OPENAI_API_CONFIGS[newIdx < idx ? newIdx : newIdx + 1];
		});
		OPENAI_API_CONFIGS = newConfig;
		await updateOpenAIHandler();
	};

	const toggleConnection = async (idx, enable) => {
		if (!OPENAI_API_CONFIGS[idx]) {
			OPENAI_API_CONFIGS[idx] = {};
		}
		OPENAI_API_CONFIGS[idx].enable = enable;
		await updateOpenAIHandler();
	};

	onMount(async () => {
		if ($user?.role === 'admin') {
			let openaiConfig = {};

			await Promise.all([
				(async () => {
					openaiConfig = await getOpenAIConfig(localStorage.token);
				})(),
				(async () => {
					connectionsConfig = await getConnectionsConfig(localStorage.token);
				})(),
				(async () => {
					const ollamaConfig = await getOllamaConfig(localStorage.token);
					ENABLE_OLLAMA_API = ollamaConfig.ENABLE_OLLAMA_API;
					OLLAMA_BASE_URLS = ollamaConfig.OLLAMA_BASE_URLS;
					OLLAMA_API_CONFIGS = ollamaConfig.OLLAMA_API_CONFIGS;
				})()
			]);

			ENABLE_OPENAI_API = openaiConfig.ENABLE_OPENAI_API;
			OPENAI_API_BASE_URLS = openaiConfig.OPENAI_API_BASE_URLS;
			OPENAI_API_KEYS = openaiConfig.OPENAI_API_KEYS;
			OPENAI_API_CONFIGS = openaiConfig.OPENAI_API_CONFIGS;

			if (!ENABLE_OPENAI_API) {
				ENABLE_OPENAI_API = true;
				await updateOpenAIHandler();
			}

			loaded = true;
		}
	});

	const submitHandler = async () => {
		await updateOpenAIHandler();
		dispatch('save');
		await config.set(await getBackendConfig());
	};
</script>

<AddConnectionModal
	bind:show={showAddConnectionModal}
	onSubmit={addConnectionHandler}
/>

<AddConnectionModal
	edit
	bind:show={showEditConnectionModal}
	connection={editConnectionIdx >= 0
		? {
				url: OPENAI_API_BASE_URLS[editConnectionIdx],
				key: OPENAI_API_KEYS[editConnectionIdx],
				config: OPENAI_API_CONFIGS[editConnectionIdx] || {}
			}
		: null}
	onSubmit={editConnectionHandler}
	onDelete={() => {
		showDeleteConfirmDialog = true;
		deleteConnectionIdx = editConnectionIdx;
	}}
/>

<ConfirmDialog
	bind:show={showDeleteConfirmDialog}
	on:confirm={() => {
		if (deleteConnectionIdx >= 0) {
			deleteConnection(deleteConnectionIdx);
			deleteConnectionIdx = -1;
			showEditConnectionModal = false;
		}
	}}
/>

<div class="flex flex-col h-full justify-between text-sm">
	<div class="overflow-y-scroll scrollbar-hidden h-full">
		{#if loaded}
			{#if OPENAI_API_BASE_URLS.length === 0}
				<!-- Empty state -->
				<div class="flex flex-col items-center justify-center h-full min-h-[300px] text-center">
					<div class="text-gray-400 dark:text-gray-500 mb-6 text-base">
						{$i18n.t('No API Connections')}
					</div>

					<button
						class="flex items-center justify-center w-20 h-20 rounded-2xl border-2 border-dashed border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 transition-all duration-200 group"
						on:click={() => {
							showAddConnectionModal = true;
						}}
						type="button"
					>
						<Plus className="size-10 text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-colors" />
					</button>

					<div class="text-xs text-gray-400 dark:text-gray-500 mt-3">
						{$i18n.t('Click to add an API connection')}
					</div>

					<div class="text-xs text-gray-400 dark:text-gray-500 mt-2 max-w-xs">
						{$i18n.t('These are global API connections, available to all users.')}
					</div>
				</div>
			{:else}
				<!-- Connection list -->
				<div class="mb-3.5">
					<div class="flex justify-between items-center mt-0.5 mb-2.5 gap-2">
						<div class="text-base font-medium shrink-0">{$i18n.t('API Connections')}</div>

						<div class="flex items-center gap-1.5 min-w-0">
							<Tooltip content={$i18n.t('These connections are shared across all users in this workspace.')}>
								<div class="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500 cursor-help truncate">
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

							<Tooltip content={$i18n.t('Add Connection')}>
								<button
									class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition shrink-0"
									on:click={() => {
										showAddConnectionModal = true;
									}}
									type="button"
								>
									<Plus className="size-4" />
								</button>
							</Tooltip>
						</div>
					</div>

					<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

				<div class="flex flex-col gap-2 mt-2">
					{#each OPENAI_API_BASE_URLS as url, idx (idx)}
							<div
								class="flex items-center gap-3 px-3 py-2.5 rounded-xl border border-gray-100 dark:border-gray-800 {!(OPENAI_API_CONFIGS[idx]?.enable ?? true)
									? 'opacity-50'
									: ''}"
							>
								<div class="flex-1 min-w-0">
									<div class="text-sm font-medium truncate">{url || $i18n.t('No URL')}</div>
									<div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
										{OPENAI_API_KEYS[idx] ? '••••••••' : $i18n.t('No API Key')}
									</div>
								</div>

								<div class="flex items-center gap-1 shrink-0">
									<Tooltip content={$i18n.t('Configure')}>
										<button
											class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition"
											on:click={() => {
												editConnectionIdx = idx;
												showEditConnectionModal = true;
											}}
											type="button"
										>
											<Cog6 className="size-4" />
										</button>
									</Tooltip>

									<Tooltip
										content={(OPENAI_API_CONFIGS[idx]?.enable ?? true)
											? $i18n.t('Enabled')
											: $i18n.t('Disabled')}
									>
										<Switch
											state={OPENAI_API_CONFIGS[idx]?.enable ?? true}
											on:change={(e) => {
												const newState = !(OPENAI_API_CONFIGS[idx]?.enable ?? true);
												toggleConnection(idx, newState);
											}}
										/>
									</Tooltip>

									<Tooltip content={$i18n.t('Delete')}>
										<button
											class="p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 text-gray-500 hover:text-red-600 dark:hover:text-red-400 transition"
											on:click={() => {
												deleteConnectionIdx = idx;
												showDeleteConfirmDialog = true;
											}}
											type="button"
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 20 20"
												fill="currentColor"
												class="size-4"
											>
												<path
													fill-rule="evenodd"
													d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022 1.005 11.07A2.611 2.611 0 007.63 19.5h4.74c1.38 0 2.529-1.08 2.61-2.48l1.006-11.07.148.022a.75.75 0 10.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z"
													clip-rule="evenodd"
												/>
											</svg>
										</button>
									</Tooltip>
							</div>
						</div>
					{/each}
				</div>

			</div>
			{/if}
		{:else}
			<div class="flex h-full justify-center">
				<div class="my-auto">
					<Spinner className="size-6" />
				</div>
			</div>
		{/if}
	</div>
</div>
