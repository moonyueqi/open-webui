<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, onMount, getContext, tick } from 'svelte';
	import { getModels as _getModels } from '$lib/apis';

	const dispatch = createEventDispatcher();
	const i18n = getContext('i18n');

	import { models, settings, user } from '$lib/stores';

	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import Connection from './Connections/Connection.svelte';

	import AddConnectionModal from '$lib/components/AddConnectionModal.svelte';

	export let saveSettings: Function;

	let config = null;

	let showConnectionModal = false;

	const addConnectionHandler = async (connection) => {
		config.OPENAI_API_BASE_URLS.push(connection.url);
		config.OPENAI_API_KEYS.push(connection.key);
		config.OPENAI_API_CONFIGS[config.OPENAI_API_BASE_URLS.length - 1] = connection.config;

		await updateHandler();
	};

	const updateHandler = async () => {
		// Remove trailing slashes
		config.OPENAI_API_BASE_URLS = config.OPENAI_API_BASE_URLS.map((url) => url.replace(/\/$/, ''));

		// Check if API KEYS length is same than API URLS length
		if (config.OPENAI_API_KEYS.length !== config.OPENAI_API_BASE_URLS.length) {
			// if there are more keys than urls, remove the extra keys
			if (config.OPENAI_API_KEYS.length > config.OPENAI_API_BASE_URLS.length) {
				config.OPENAI_API_KEYS = config.OPENAI_API_KEYS.slice(
					0,
					config.OPENAI_API_BASE_URLS.length
				);
			}

			// if there are more urls than keys, add empty keys
			if (config.OPENAI_API_KEYS.length < config.OPENAI_API_BASE_URLS.length) {
				const diff = config.OPENAI_API_BASE_URLS.length - config.OPENAI_API_KEYS.length;
				for (let i = 0; i < diff; i++) {
					config.OPENAI_API_KEYS.push('');
				}
			}
		}

		await saveSettings({
			directConnections: config
		});
	};

	onMount(async () => {
		config = $settings?.directConnections ?? {
			OPENAI_API_BASE_URLS: [],
			OPENAI_API_KEYS: [],
			OPENAI_API_CONFIGS: {}
		};
	});
</script>

<AddConnectionModal direct bind:show={showConnectionModal} onSubmit={addConnectionHandler} />

<form
	id="tab-connections"
	class="flex flex-col h-full justify-between text-sm"
	on:submit|preventDefault={() => {
		updateHandler();
	}}
>
	<div class="overflow-y-auto scrollbar-hidden h-full">
		{#if config !== null}
			{#if (config?.OPENAI_API_BASE_URLS ?? []).length === 0}
				<div class="flex flex-col items-center justify-center h-full min-h-[14rem] text-center">
					<div class="p-4 rounded-2xl bg-gray-50 dark:bg-gray-800/50 mb-4">
						<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-8 text-gray-300 dark:text-gray-600">
							<path d="M1 9.5A3.5 3.5 0 0 0 4.5 13H12a3 3 0 0 0 .917-5.857 2.503 2.503 0 0 0-3.198-3.019 3.5 3.5 0 0 0-6.628 2.171A3.5 3.5 0 0 0 1 9.5Z" />
						</svg>
					</div>
					<div class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
						{$i18n.t('No API Connections')}
					</div>
					<div class="text-xs text-gray-400 dark:text-gray-500 mb-4">
						{$i18n.t('Add a connection to get started')}
					</div>

					<button
						class="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-900 dark:bg-white text-white dark:text-gray-900 text-sm font-medium hover:bg-gray-800 dark:hover:bg-gray-100 transition-all shadow-sm"
						on:click={() => {
							showConnectionModal = true;
						}}
						type="button"
					>
						<Plus className="size-4" />
						<span>{$i18n.t('Add Connection')}</span>
					</button>
				</div>
			{:else}
				<div>
					<div class="flex justify-between items-center mb-3">
						<div class="font-medium text-gray-700 dark:text-gray-200">{$i18n.t('API Connections')}</div>

						<Tooltip content={$i18n.t('Add Connection')}>
							<button
								class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
								aria-label={$i18n.t('Add Connection')}
								on:click={() => {
									showConnectionModal = true;
								}}
								type="button"
							>
								<Plus className="size-4" />
							</button>
						</Tooltip>
					</div>

					<div class="flex flex-col gap-2">
						{#each config?.OPENAI_API_BASE_URLS ?? [] as url, idx}
							<Connection
								bind:url
								bind:key={config.OPENAI_API_KEYS[idx]}
								bind:config={config.OPENAI_API_CONFIGS[idx]}
								onSubmit={() => {
									updateHandler();
								}}
								onDelete={() => {
									config.OPENAI_API_BASE_URLS = config.OPENAI_API_BASE_URLS.filter(
										(url, urlIdx) => idx !== urlIdx
									);
									config.OPENAI_API_KEYS = config.OPENAI_API_KEYS.filter(
										(key, keyIdx) => idx !== keyIdx
									);

									let newConfig = {};
									config.OPENAI_API_BASE_URLS.forEach((url, newIdx) => {
										newConfig[newIdx] =
											config.OPENAI_API_CONFIGS[newIdx < idx ? newIdx : newIdx + 1];
									});
									config.OPENAI_API_CONFIGS = newConfig;
								}}
							/>
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

	<div class="flex justify-end pt-5 mt-4 border-t border-gray-100 dark:border-gray-800">
		<button
			class="px-5 py-2 text-sm font-medium bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 transition-all rounded-lg shadow-sm"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</form>
