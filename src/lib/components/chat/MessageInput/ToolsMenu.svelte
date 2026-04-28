<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { getContext, tick } from 'svelte';
	import { flyAndScale } from '$lib/utils/transitions';

	import { tools as _tools, toolServers, user } from '$lib/stores';

	import { getOAuthClientAuthorizationUrl } from '$lib/apis/configs';
	import { getTools } from '$lib/apis/tools';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Wrench from '$lib/components/icons/Wrench.svelte';
	import Knobs from '$lib/components/icons/Knobs.svelte';
	import Check from '$lib/components/icons/Check.svelte';

	const i18n = getContext('i18n');

	export let selectedToolIds: string[] = [];

	export let onShowValves: (e: { type: string; id: string }) => void = () => {};
	export let onClose: () => void = () => {};
	export let closeOnOutsideClick = true;

	let show = false;
	let tools: Record<string, any> | null = null;

	$: if (show) {
		init();
	}

	$: if (tools) {
		for (const id of Object.keys(tools)) {
			tools[id].enabled = selectedToolIds.includes(id);
		}
	}

	const init = async () => {
		if ($_tools === null) {
			await _tools.set(await getTools(localStorage.token));
		}

		const next: Record<string, any> = {};

		if ($_tools) {
			for (const tool of $_tools) {
				next[tool.id] = {
					name: tool.name,
					description: tool?.meta?.description ?? '',
					enabled: selectedToolIds.includes(tool.id),
					...tool
				};
			}
		}

		if ($toolServers) {
			for (const serverIdx in $toolServers) {
				const server = $toolServers[serverIdx];
				if (server?.info && !`${serverIdx}`.startsWith('terminal_')) {
					const id = `direct_server:${serverIdx}`;
					next[id] = {
						name: server?.info?.title ?? server.url,
						description: server.info.description ?? '',
						enabled: selectedToolIds.includes(id)
					};
				}
			}
		}

		tools = next;

		selectedToolIds = selectedToolIds.filter(
			(id) => Object.keys(tools ?? {}).includes(id) || id.startsWith('direct_server:terminal_')
		);
	};

	const toggleTool = async (toolId: string) => {
		if (!tools) return;

		if (!(tools[toolId]?.authenticated ?? true)) {
			let parts = toolId.split(':');
			let serverId = parts?.at(-1) ?? toolId;
			const authUrl = getOAuthClientAuthorizationUrl(serverId, 'mcp');
			window.open(authUrl, '_self', 'noopener');
			return;
		}

		tools[toolId].enabled = !tools[toolId].enabled;
		const state = tools[toolId].enabled;
		await tick();

		if (state) {
			selectedToolIds = [...selectedToolIds, toolId];
		} else {
			selectedToolIds = selectedToolIds.filter((id) => id !== toolId);
		}
	};

	$: visibleSelectedCount = (selectedToolIds ?? []).filter(
		(id) => !id.startsWith('direct_server:terminal_')
	).length;
</script>

<Dropdown
	bind:show
	{closeOnOutsideClick}
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<Tooltip content={$i18n.t('Tools')} placement="top">
		<button
			type="button"
			class="flex gap-1 items-center px-2.5 h-8 text-sm rounded-full transition-colors duration-200 outline-hidden focus:outline-hidden {visibleSelectedCount >
			0
				? 'text-sky-600 dark:text-sky-300 bg-sky-50 hover:bg-sky-100 dark:bg-sky-500/10 dark:hover:bg-sky-500/15'
				: 'text-gray-700 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-800'}"
		>
			<Wrench className="size-4" strokeWidth="1.75" />
			<span class="text-xs font-medium whitespace-nowrap">{$i18n.t('Tools')}</span>
			{#if visibleSelectedCount > 0}
				<span class="text-xs font-medium opacity-80">{visibleSelectedCount}</span>
			{/if}
		</button>
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="w-56 rounded-2xl px-1 py-1 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-lg max-h-80 overflow-hidden"
			sideOffset={4}
			alignOffset={-6}
			side="top"
			align="start"
			transition={flyAndScale}
		>
			{#if !tools}
				<div class="flex items-center justify-center py-6 text-sm text-gray-500">
					<Spinner className="size-4" />
				</div>
			{:else}
				<div class="overflow-y-auto max-h-72 py-0.5">
					{#if Object.keys(tools).length === 0}
						<div class="px-3 py-4 text-center text-sm text-gray-500">
							{$i18n.t('No results found')}
						</div>
					{:else}
						{#each Object.keys(tools) as toolId (toolId)}
							<Tooltip content={tools[toolId]?.description || tools[toolId]?.name || ''} placement="right">
								<div
									class="relative flex w-full items-center gap-2 px-2.5 py-1.5 text-sm rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50"
								>
									{#if !(tools[toolId]?.authenticated ?? true)}
										<div class="absolute inset-0 opacity-50 rounded-xl cursor-pointer z-10" />
									{/if}

									<button
										type="button"
										class="flex flex-1 min-w-0 items-center gap-2 text-left cursor-pointer"
										on:click={() => toggleTool(toolId)}
									>
										<div class="shrink-0">
											<Wrench
												className="size-4 {tools[toolId].enabled
													? 'text-sky-500'
													: 'text-gray-400'}"
												strokeWidth="1.75"
											/>
										</div>
										<div class="flex-1 min-w-0">
											<div
												class="text-xs truncate {tools[toolId].enabled
													? 'text-sky-600 dark:text-sky-300 font-medium'
													: 'text-gray-700 dark:text-gray-300'}"
											>
												{tools[toolId].name}
											</div>
										</div>
									</button>

									{#if tools[toolId]?.has_user_valves && ($user?.role === 'admin' || ($user?.permissions?.chat?.valves ?? true))}
										<Tooltip content={$i18n.t('Valves')}>
											<button
												class="shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition rounded-full"
												type="button"
												on:click={(e) => {
													e.stopPropagation();
													e.preventDefault();
													onShowValves({
														type: 'tool',
														id: toolId
													});
												}}
											>
												<Knobs className="size-3.5" />
											</button>
										</Tooltip>
									{/if}

									{#if tools[toolId].enabled}
										<div class="shrink-0 text-sky-500">
											<Check className="size-3.5" strokeWidth="2.5" />
										</div>
									{/if}
								</div>
							</Tooltip>
						{/each}
					{/if}
				</div>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
