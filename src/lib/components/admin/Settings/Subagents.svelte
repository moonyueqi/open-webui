<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { getBackendConfig } from '$lib/apis';
	import { getSubagentsConfig, updateSubagentsConfig } from '$lib/apis/auths';
	import { config } from '$lib/stores';
	import Switch from '$lib/components/common/Switch.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext('i18n');

	export let saveHandler: Function = () => {};

	let subagentsConfig = null;

	const updateHandler = async () => {
		const res = await updateSubagentsConfig(localStorage.token, subagentsConfig);
		await config.set(await getBackendConfig());

		if (res) {
			saveHandler();
		} else {
			toast.error($i18n.t('Failed to update settings'));
		}
	};

	onMount(async () => {
		subagentsConfig = await getSubagentsConfig(localStorage.token);
	});
</script>

<form
	class="flex flex-col h-full justify-between space-y-3 text-sm"
	on:submit|preventDefault={async () => {
		updateHandler();
	}}
>
	<div class="space-y-3 overflow-y-scroll scrollbar-hidden h-full">
		{#if subagentsConfig !== null}
			<div>
				<div class="mt-0.5 mb-2.5 text-base font-medium">{$i18n.t('Sub-agents')}</div>
				<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

				<div class="mb-2.5 flex w-full items-center justify-between pr-2">
					<Tooltip
						content={$i18n.t(
							'Allow models to delegate focused sub-tasks to helper agents via the delegate_task tool. Each sub-agent uses the same model and tools as the parent chat.'
						)}
						placement="top-start"
					>
						<div class="self-center text-xs font-medium">
							{$i18n.t('Enable Sub-agents')}
						</div>
					</Tooltip>
					<Switch bind:state={subagentsConfig.ENABLE_SUBAGENTS} />
				</div>

				<div class="mb-2.5 flex w-full items-center justify-between pr-2">
					<div class="self-center text-xs font-medium">
						{$i18n.t('Max Concurrent Sub-agents')}
					</div>
					<input
						class="w-24 rounded-lg px-2 py-1 text-xs bg-gray-50 dark:bg-gray-850 outline-none"
						type="number"
						min="1"
						bind:value={subagentsConfig.SUBAGENTS_MAX_CONCURRENT}
					/>
				</div>

				<div class="mb-2.5 flex w-full items-center justify-between pr-2">
					<div class="self-center text-xs font-medium">
						{$i18n.t('Max Tool Iterations per Sub-agent')}
					</div>
					<input
						class="w-24 rounded-lg px-2 py-1 text-xs bg-gray-50 dark:bg-gray-850 outline-none"
						type="number"
						min="1"
						bind:value={subagentsConfig.SUBAGENTS_MAX_ITERATIONS}
					/>
				</div>

				<div class="mb-2.5 flex w-full items-center justify-between pr-2">
					<div class="self-center text-xs font-medium">
						{$i18n.t('Max Output Characters')}
					</div>
					<input
						class="w-24 rounded-lg px-2 py-1 text-xs bg-gray-50 dark:bg-gray-850 outline-none"
						type="number"
						min="1000"
						bind:value={subagentsConfig.SUBAGENTS_MAX_OUTPUT}
					/>
				</div>

				<div class="mb-2.5">
					<div class="self-center text-xs font-medium mb-1">
						{$i18n.t('Sub-agents System Prompt')}
					</div>
					<Textarea
						bind:value={subagentsConfig.SUBAGENTS_SYSTEM_PROMPT}
						placeholder={$i18n.t('Leave empty to use the built-in sub-agent system prompt')}
					/>
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
</form>
