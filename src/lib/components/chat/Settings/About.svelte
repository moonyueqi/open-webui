<script lang="ts">
	import { getOllamaVersion } from '$lib/apis/ollama';
	import { WEBUI_NAME } from '$lib/stores';
	import { onMount, getContext } from 'svelte';

	const i18n = getContext('i18n');

	let ollamaVersion = '';

	onMount(async () => {
		ollamaVersion = await getOllamaVersion(localStorage.token).catch((error) => {
			return '';
		});
	});
</script>

<div id="tab-about" class="flex flex-col h-full text-sm">
	<div class="space-y-4">
		<div class="flex items-center gap-4 p-4 rounded-xl bg-gray-50 dark:bg-gray-800/40 border border-gray-100 dark:border-gray-800">
			<div class="flex-shrink-0 p-2.5 rounded-xl bg-white dark:bg-gray-700/50 shadow-sm">
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-6 text-gray-600 dark:text-gray-300">
					<path fill-rule="evenodd" d="M2.25 6a3 3 0 0 1 3-3h13.5a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H5.25a3 3 0 0 1-3-3V6Zm3.97.97a.75.75 0 0 1 1.06 0l2.25 2.25a.75.75 0 0 1 0 1.06l-2.25 2.25a.75.75 0 0 1-1.06-1.06l1.72-1.72-1.72-1.72a.75.75 0 0 1 0-1.06Zm4.28 4.28a.75.75 0 0 0 0 1.5h3a.75.75 0 0 0 0-1.5h-3Z" clip-rule="evenodd" />
				</svg>
			</div>
			<div class="flex-1">
				<div class="text-sm font-semibold text-gray-800 dark:text-gray-100">{$WEBUI_NAME}</div>
				<div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{$i18n.t('Version')}</div>
			</div>
			<div class="px-3 py-1 rounded-full bg-white dark:bg-gray-700/50 border border-gray-200/60 dark:border-gray-600/40 text-xs font-mono font-medium text-gray-600 dark:text-gray-300 shadow-sm">
				v2.1.0
			</div>
		</div>

		{#if ollamaVersion}
			<div class="flex items-center gap-4 p-4 rounded-xl bg-gray-50 dark:bg-gray-800/40 border border-gray-100 dark:border-gray-800">
				<div class="flex-shrink-0 p-2.5 rounded-xl bg-white dark:bg-gray-700/50 shadow-sm">
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-6 text-gray-600 dark:text-gray-300">
						<path d="M12 .75a8.25 8.25 0 0 0-4.135 15.39c.686.398 1.115 1.008 1.134 1.623a.75.75 0 0 0 .577.706c.352.083.71.148 1.074.195.323.041.6-.218.6-.544v-4.661a6.714 6.714 0 0 1-.937-.171.75.75 0 1 1 .374-1.453 5.261 5.261 0 0 0 2.626 0 .75.75 0 1 1 .374 1.452 6.712 6.712 0 0 1-.937.172v4.66c0 .327.277.586.6.545.364-.047.722-.112 1.074-.195a.75.75 0 0 0 .577-.706c.02-.615.448-1.225 1.134-1.623A8.25 8.25 0 0 0 12 .75Z" />
						<path fill-rule="evenodd" d="M9.013 19.9a.75.75 0 0 1 .877-.597 11.319 11.319 0 0 0 4.22 0 .75.75 0 1 1 .28 1.473 12.819 12.819 0 0 1-4.78 0 .75.75 0 0 1-.597-.876ZM9.754 22.344a.75.75 0 0 1 .824-.668 13.682 13.682 0 0 0 2.844 0 .75.75 0 1 1 .156 1.492 15.156 15.156 0 0 1-3.156 0 .75.75 0 0 1-.668-.824Z" clip-rule="evenodd" />
					</svg>
				</div>
				<div class="flex-1">
					<div class="text-sm font-semibold text-gray-800 dark:text-gray-100">Ollama</div>
					<div class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{$i18n.t('Ollama Version')}</div>
				</div>
				<div class="px-3 py-1 rounded-full bg-white dark:bg-gray-700/50 border border-gray-200/60 dark:border-gray-600/40 text-xs font-mono font-medium text-gray-600 dark:text-gray-300 shadow-sm">
					{ollamaVersion ?? 'N/A'}
				</div>
			</div>
		{/if}
	</div>
</div>
