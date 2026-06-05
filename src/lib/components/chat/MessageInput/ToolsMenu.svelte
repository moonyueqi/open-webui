<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { getContext, tick } from 'svelte';
	import { flyAndScale } from '$lib/utils/transitions';

	import { tools as _tools, toolServers, user } from '$lib/stores';

	import { getOAuthClientAuthorizationUrl } from '$lib/apis/configs';
	import { getTools } from '$lib/apis/tools';
	import { getToolCategories } from '$lib/apis/tool-categories';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Wrench from '$lib/components/icons/Wrench.svelte';
	import Knobs from '$lib/components/icons/Knobs.svelte';
	import Check from '$lib/components/icons/Check.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';

	const i18n = getContext('i18n');

	const MCP_GROUP_ID = '__mcp_servers__';

	export let selectedToolIds: string[] = [];

	export let onShowValves: (e: { type: string; id: string }) => void = () => {};
	export let onClose: () => void = () => {};
	export let closeOnOutsideClick = true;

	let show = false;
	let loading = false;

	let tools: Record<string, any> | null = null;
	let categories: any[] = [];

	let expandedGroupId: string | null = null;

	$: if (show) {
		init();
	}

	$: if (tools) {
		for (const id of Object.keys(tools)) {
			tools[id].enabled = selectedToolIds.includes(id);
		}
	}

	const init = async () => {
		loading = true;

		if ($_tools === null) {
			await _tools.set(await getTools(localStorage.token));
		}

		if (categories.length === 0) {
			try {
				const catRes = await getToolCategories(localStorage.token).catch(() => null);
				if (catRes?.items) {
					categories = catRes.items;
				}
			} catch {
				categories = [];
			}
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
						enabled: selectedToolIds.includes(id),
						__is_mcp: true
					};
				}
			}
		}

		tools = next;

		selectedToolIds = selectedToolIds.filter(
			(id) => Object.keys(tools ?? {}).includes(id) || id.startsWith('direct_server:terminal_')
		);

		loading = false;
	};

	$: groupedTools = (() => {
		if (!tools) return [] as { id: string; name: string; description?: string; items: any[] }[];

		const byCategory: Record<string, any[]> = {};
		const serverTools: any[] = [];

		for (const id of Object.keys(tools)) {
			const t = tools[id];
			// 工具服务器（管理员"扩展功能"配置的 OpenAPI/MCP 服务器，以及用户在
			// 个人设置里直连的工具服务器）独立成组，不参与按分类的分组。
			if (t?.__is_mcp || id.startsWith('server:') || id.startsWith('direct_server:')) {
				serverTools.push({ id, ...t });
				continue;
			}
			const cid = t?.category_id;
			if (!cid) continue; // 未分类不显示
			if (!byCategory[cid]) byCategory[cid] = [];
			byCategory[cid].push({ id, ...t });
		}

		const groups: { id: string; name: string; description?: string; items: any[] }[] = [];

		for (const cat of categories) {
			const items = byCategory[cat.id] ?? [];
			if (items.length === 0) continue; // 空分类不显示
			groups.push({
				id: cat.id,
				name: cat.name,
				description: cat.description,
				items
			});
		}

		if (serverTools.length > 0) {
			groups.push({
				id: MCP_GROUP_ID,
				name: $i18n.t('Tool Servers'),
				description: $i18n.t('Connected OpenAPI / MCP tool servers'),
				items: serverTools
			});
		}

		return groups;
	})();

	function toggleGroup(groupId: string) {
		expandedGroupId = expandedGroupId === groupId ? null : groupId;
	}

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
			expandedGroupId = null;
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
			{#if loading || !tools}
				<div class="flex items-center justify-center py-6 text-sm text-gray-500">
					<Spinner className="size-4" />
				</div>
			{:else}
				<div class="overflow-y-auto max-h-72 py-0.5">
					{#if groupedTools.length === 0}
						<div class="px-3 py-4 text-center text-sm text-gray-500">
							{$i18n.t('No results found')}
						</div>
					{:else}
						{#each groupedTools as group (group.id)}
							<div
								class="px-2.5 py-1.5 rounded-xl w-full text-left flex justify-between items-center text-sm hover:bg-gray-50 dark:hover:bg-gray-800/50"
							>
								<button
									class="w-full flex-1 flex items-center gap-1.5"
									type="button"
									on:click={() => toggleGroup(group.id)}
								>
									<div class="shrink-0">
										{#if expandedGroupId === group.id}
											<ChevronDown className="size-3 text-gray-400" />
										{:else}
											<ChevronRight className="size-3 text-gray-400" />
										{/if}
									</div>

									<svg
										xmlns="http://www.w3.org/2000/svg"
										fill="none"
										viewBox="0 0 24 24"
										stroke-width="1.5"
										stroke="currentColor"
										class="size-4 text-sky-500 shrink-0"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z"
										/>
									</svg>

									<Tooltip
										content={group.description || group.name}
										placement="top-start"
										className="flex flex-1 min-w-0"
									>
										<div class="line-clamp-1 flex-1 text-sm font-medium">
											{group.name}
										</div>
									</Tooltip>

									<span class="shrink-0 text-xs text-gray-400">
										{group.items.length}
									</span>
								</button>
							</div>

							{#if expandedGroupId === group.id}
								<div class="pl-6 mb-1 flex flex-col gap-0.5">
									{#each group.items as toolItem (toolItem.id)}
										{@const toolId = toolItem.id}
										<Tooltip
											content={tools[toolId]?.description ||
												tools[toolId]?.name ||
												''}
											placement="right"
										>
											<div
												class="relative flex w-full items-center gap-2 px-2.5 py-1.5 text-sm rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50"
											>
												{#if !(tools[toolId]?.authenticated ?? true)}
													<div
														class="absolute inset-0 opacity-50 rounded-xl cursor-pointer z-10"
													/>
												{/if}

												<button
													type="button"
													class="flex flex-1 min-w-0 items-center gap-2 text-left cursor-pointer"
													on:click={() => toggleTool(toolId)}
												>
													<div class="shrink-0">
														<Wrench
															className="size-3.5 {tools[toolId].enabled
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
								</div>
							{/if}
						{/each}
					{/if}
				</div>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
