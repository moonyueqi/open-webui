<script lang="ts">
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { toast } from 'svelte-sonner';
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { user, tools as _toolsStore } from '$lib/stores';
	import {
		getToolCategoryById,
		updateToolCategoryById,
		getToolsByCategoryId,
		updateToolCategoryAccessGrants
	} from '$lib/apis/tool-categories';
	import { deleteToolById, getToolById, getTools } from '$lib/apis/tools';
	import { capitalizeFirstLetter } from '$lib/utils';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Badge from '$lib/components/common/Badge.svelte';
	import AccessControlModal from '../common/AccessControlModal.svelte';
	import ValvesModal from '../common/ValvesModal.svelte';
	import ManifestModal from '../common/ManifestModal.svelte';
	import ViewSelector from '../common/ViewSelector.svelte';
	import ToolMenu from './ToolMenu.svelte';
	import Plus from '../../icons/Plus.svelte';
	import GarbageBin from '../../icons/GarbageBin.svelte';
	import EllipsisHorizontal from '../../icons/EllipsisHorizontal.svelte';
	import Search from '../../icons/Search.svelte';
	import XMark from '../../icons/XMark.svelte';

	const i18n = getContext('i18n');

	let id: string;
	let category: any = null;
	let toolItems: any[] | null = null;
	let toolsTotal: number | null = null;
	let toolsPage = 1;
	let loading = false;

	let shiftKey = false;
	let selectedTool: any = null;
	let showDeleteConfirm = false;
	let showAccessControlModal = false;
	let showManifestModal = false;
	let showValvesModal = false;

	let query = '';
	let viewOption = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;

	let editName = '';
	let editDescription = '';
	let debounceTimeout: ReturnType<typeof setTimeout> | null = null;

	const loadCategory = async () => {
		const res = await getToolCategoryById(localStorage.token, id).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			category = res;
			editName = category.name ?? '';
			editDescription = category.description ?? '';
			if (!Array.isArray(category?.access_grants)) {
				category.access_grants = [];
			}
		} else {
			goto('/workspace/tools');
		}
	};

	const loadTools = async () => {
		loading = true;
		const res = await getToolsByCategoryId(
			localStorage.token,
			id,
			toolsPage,
			query,
			viewOption
		).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toolItems = res.items;
			toolsTotal = res.total;
		}
		loading = false;
	};

	$: if (id && query !== undefined) {
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			toolsPage = 1;
			loadTools();
		}, 300);
	}

	$: if (id && viewOption !== undefined) {
		toolsPage = 1;
		loadTools();
	}

	$: if (toolsPage && id) {
		loadTools();
	}

	const cloneHandler = async (tool: any) => {
		const _tool = await getToolById(localStorage.token, tool.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (_tool) {
			sessionStorage.tool = JSON.stringify({
				..._tool,
				id: `${_tool.id}_clone`,
				name: `${_tool.name} (Clone)`
			});
			goto(`/workspace/tools/create?category_id=${id}`);
		}
	};

	const exportHandler = async (tool: any) => {
		const _tool = await getToolById(localStorage.token, tool.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (_tool) {
			const blob = new Blob([JSON.stringify([_tool])], {
				type: 'application/json'
			});
			saveAs(blob, `tool-${_tool.id}-export-${Date.now()}.json`);
		}
	};

	const deleteToolHandler = async (tool: any) => {
		const res = await deleteToolById(localStorage.token, tool.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Tool deleted successfully'));
			await _toolsStore.set(await getTools(localStorage.token));
		}

		toolsPage = 1;
		loadTools();
	};

	const changeDebounceHandler = () => {
		if (debounceTimeout) {
			clearTimeout(debounceTimeout);
		}

		debounceTimeout = setTimeout(async () => {
			if (editName.trim() === '') {
				toast.error($i18n.t('Category name cannot be empty'));
				return;
			}

			const res = await updateToolCategoryById(
				localStorage.token,
				id,
				editName,
				editDescription,
				null
			).catch((e) => {
				toast.error($i18n.t(`${e}`));
				return null;
			});

			if (res) {
				category = res;
				editName = category.name ?? '';
				editDescription = category.description ?? '';
				toast.success($i18n.t('Saved'));
			}
		}, 1000);
	};

	onMount(async () => {
		id = $page.params.id;
		await loadCategory();

		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Shift') shiftKey = true;
		};
		const onKeyUp = (event: KeyboardEvent) => {
			if (event.key === 'Shift') shiftKey = false;
		};
		const onBlur = () => {
			shiftKey = false;
		};

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);
		window.addEventListener('blur', onBlur);

		return () => {
			clearTimeout(searchDebounceTimer);
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);
			window.removeEventListener('blur', onBlur);
		};
	});
</script>

{#if category}
	<DeleteConfirmDialog
		bind:show={showDeleteConfirm}
		title={$i18n.t('Delete tool?')}
		on:confirm={() => {
			deleteToolHandler(selectedTool);
		}}
	>
		<div class="text-sm text-gray-500 truncate">
			{$i18n.t('This will delete')} <span class="font-medium">{selectedTool?.name}</span>.
		</div>
	</DeleteConfirmDialog>

	<AccessControlModal
		bind:show={showAccessControlModal}
		bind:accessGrants={category.access_grants}
		accessRoles={['read', 'write']}
		share={$user?.permissions?.sharing?.tools || $user?.role === 'admin'}
		sharePublic={$user?.permissions?.sharing?.public_tools || $user?.role === 'admin'}
		shareUsers={($user?.permissions?.access_grants?.allow_users ?? true) || $user?.role === 'admin'}
		onChange={async () => {
			try {
				await updateToolCategoryAccessGrants(
					localStorage.token,
					id,
					category.access_grants
				);
				toast.success($i18n.t('Saved'));
			} catch (error) {
				toast.error(`${error}`);
			}
		}}
	/>

	<ManifestModal bind:show={showManifestModal} manifest={selectedTool?.meta?.manifest ?? {}} />
	<ValvesModal bind:show={showValvesModal} type="tool" id={selectedTool?.id ?? null} />

	<div class="flex flex-col w-full h-full min-h-0">
		<div class="flex flex-col gap-2 px-1 mt-1.5 mb-4 shrink-0">
			<div class="flex justify-between items-center">
				<div class="flex items-center gap-3 min-w-0 flex-1">
					<button
						class="flex items-center justify-center w-9 h-9 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 transition-colors shrink-0"
						aria-label={$i18n.t('Back')}
						on:click={() => goto('/workspace/tools')}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 20 20"
							fill="currentColor"
							class="w-4 h-4"
						>
							<path
								fill-rule="evenodd"
								d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z"
								clip-rule="evenodd"
							/>
						</svg>
					</button>

					<div class="min-w-0 flex-1">
						<div class="flex items-center gap-2">
							<input
								type="text"
								class="text-xl font-semibold bg-transparent outline-hidden border-none p-0 focus:ring-0 w-full"
								bind:value={editName}
								aria-label={$i18n.t('Category Name')}
								placeholder={$i18n.t('Category Name')}
								disabled={$user?.role !== 'admin'}
								on:input={() => {
									changeDebounceHandler();
								}}
							/>
						</div>
						<div class="flex items-center gap-2">
							<input
								type="text"
								class="text-xs text-gray-500 dark:text-gray-400 bg-transparent outline-hidden border-none p-0 w-full focus:ring-0"
								bind:value={editDescription}
								aria-label={$i18n.t('Description')}
								placeholder={$i18n.t('Add a description')}
								disabled={$user?.role !== 'admin'}
								on:input={() => {
									changeDebounceHandler();
								}}
							/>
						</div>
					</div>
				</div>

				<div class="flex items-center gap-2 shrink-0">
					{#if $user?.role === 'admin'}
						<button
							class="bg-gray-50 hover:bg-gray-100 text-black dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-white transition px-2.5 py-1 rounded-full flex gap-1.5 items-center text-sm border border-gray-100 dark:border-gray-800"
							on:click={() => (showAccessControlModal = true)}
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="2.5"
								stroke="currentColor"
								class="size-3.5"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z"
								/>
							</svg>
							{$i18n.t('Access')}
						</button>
					{/if}

					{#if category.write_access}
						<a
							class="px-3 py-1.5 rounded-xl bg-gray-100 hover:bg-gray-200 text-black dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
							href={`/workspace/tools/create?category_id=${id}`}
						>
							<Plus className="size-3.5" strokeWidth="2.5" />
							<div class="hidden md:block text-xs">{$i18n.t('New Tool')}</div>
						</a>
					{/if}
				</div>
			</div>
		</div>

		<div
			class="py-2.5 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm min-h-0 flex flex-col overflow-hidden flex-1"
		>
			<div class="flex w-full space-x-2 py-0.5 px-4 pb-2.5 shrink-0">
				<div
					class="flex flex-1 items-center bg-gray-50 dark:bg-gray-850 rounded-xl px-3 py-1.5 transition focus-within:ring-2 focus-within:ring-gray-300/50 dark:focus-within:ring-gray-600/50 focus-within:bg-white dark:focus-within:bg-gray-900"
				>
					<Search className="size-3.5 text-gray-400 shrink-0" />
					<input
						class="w-full text-sm py-0.5 pl-2 outline-hidden bg-transparent placeholder:text-gray-400"
						bind:value={query}
						aria-label={$i18n.t('Search Tools')}
						placeholder={$i18n.t('Search Tools')}
					/>
					{#if query}
						<button
							class="p-0.5 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition ml-1"
							aria-label={$i18n.t('Clear search')}
							on:click={() => {
								query = '';
							}}
						>
							<XMark className="size-3" strokeWidth="2" />
						</button>
					{/if}
				</div>
			</div>

			<div
				class="px-3.5 flex w-full bg-transparent overflow-x-auto scrollbar-none shrink-0"
				on:wheel={(e) => {
					if (e.deltaY !== 0) {
						e.preventDefault();
						e.currentTarget.scrollLeft += e.deltaY;
					}
				}}
			>
				<div
					class="flex gap-0.5 w-fit text-center text-sm rounded-full bg-transparent px-1 whitespace-nowrap"
				>
					<ViewSelector bind:value={viewOption} />
				</div>
			</div>

			{#if toolItems === null || loading}
				<div class="w-full flex justify-center items-center py-16 flex-1">
					<Spinner className="size-5" />
				</div>
			{:else if (toolItems ?? []).length !== 0}
				<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden px-3 mt-2">
					<div class="gap-2.5 grid lg:grid-cols-2">
						{#each toolItems as tool (tool.id)}
							{@const isServer = String(tool.id ?? '').startsWith('server:')}
							{@const isMcp = String(tool.id ?? '').startsWith('server:mcp:')}
							{@const canEdit = !!tool.write_access && !isServer}
							<div
								class="group flex text-left w-full px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-850/60 transition-all duration-200 rounded-xl border border-transparent hover:border-gray-200/60 dark:hover:border-gray-700/40 hover:shadow-sm {canEdit
									? ''
									: 'opacity-80'}"
							>
								<div class="flex items-start gap-3 flex-1 min-w-0">
									<div
										class="flex items-center justify-center w-10 h-10 rounded-lg bg-sky-50 dark:bg-sky-500/10 shrink-0 mt-0.5 group-hover:bg-sky-100 dark:group-hover:bg-sky-500/20 transition-colors"
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="1.5"
											stroke="currentColor"
											class="size-5 text-sky-600 dark:text-sky-400"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z"
											/>
										</svg>
									</div>

									{#if canEdit}
										<a
											class="flex-1 min-w-0"
											href={`/workspace/tools/edit?id=${encodeURIComponent(tool.id)}`}
										>
											<div class="flex items-center gap-2">
												<Tooltip
													content={tool?.meta?.description ?? tool.name}
													placement="top-start"
												>
													<div class="text-sm font-semibold line-clamp-1">{tool.name}</div>
												</Tooltip>
												{#if tool?.meta?.manifest?.version}
													<div class="text-xs text-sky-500 dark:text-sky-400 font-mono shrink-0">
														v{tool?.meta?.manifest?.version ?? ''}
													</div>
												{/if}
											</div>
											{#if tool?.meta?.description}
												<div class="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">
													{tool?.meta?.description}
												</div>
											{/if}
											<div
												class="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500 mt-0.5"
											>
												<Tooltip
													content={tool?.user?.email ?? $i18n.t('Deleted User')}
													className="flex shrink-0"
													placement="top-start"
												>
													<span class="shrink-0">
														{$i18n.t('By {{name}}', {
															name: capitalizeFirstLetter(
																tool?.user?.name ??
																	tool?.user?.email ??
																	$i18n.t('Deleted User')
															)
														})}
													</span>
												</Tooltip>
												{#if tool?.updated_at}
													<span class="text-gray-300 dark:text-gray-600">·</span>
													<Tooltip content={dayjs(tool.updated_at * 1000).format('LLLL')}>
														<span class="shrink-0">
															{$i18n.t('Updated')}
															{dayjs(tool.updated_at * 1000).fromNow()}
														</span>
													</Tooltip>
												{/if}
											</div>
										</a>
									{:else}
										<div class="flex-1 min-w-0">
											<div class="flex items-center justify-between gap-2">
												<Tooltip
													content={tool?.meta?.description ?? tool.name}
													placement="top-start"
												>
													<div class="flex items-center gap-2">
														<div class="text-sm font-semibold line-clamp-1">{tool.name}</div>
														{#if tool?.meta?.manifest?.version}
															<div class="text-xs text-sky-500 dark:text-sky-400 font-mono shrink-0">
																v{tool?.meta?.manifest?.version ?? ''}
															</div>
														{/if}
													</div>
												</Tooltip>
												{#if isServer}
													<Badge
														type="info"
														content={isMcp ? $i18n.t('MCP') : $i18n.t('OpenAPI')}
													/>
												{:else}
													<Badge type="muted" content={$i18n.t('Read Only')} />
												{/if}
											</div>
											{#if tool?.meta?.description}
												<div class="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">
													{tool?.meta?.description}
												</div>
											{/if}
											<div
												class="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500 mt-0.5"
											>
												{#if isServer}
													<span class="shrink-0">
														{$i18n.t('Managed by administrator')}
													</span>
												{:else}
													<Tooltip
														content={tool?.user?.email ?? $i18n.t('Deleted User')}
														className="flex shrink-0"
														placement="top-start"
													>
														<span class="shrink-0">
															{$i18n.t('By {{name}}', {
																name: capitalizeFirstLetter(
																	tool?.user?.name ??
																		tool?.user?.email ??
																		$i18n.t('Deleted User')
																)
															})}
														</span>
													</Tooltip>
												{/if}
												{#if tool?.updated_at}
													<span class="text-gray-300 dark:text-gray-600">·</span>
													<Tooltip content={dayjs(tool.updated_at * 1000).format('LLLL')}>
														<span class="shrink-0">
															{$i18n.t('Updated')}
															{dayjs(tool.updated_at * 1000).fromNow()}
														</span>
													</Tooltip>
												{/if}
											</div>
										</div>
									{/if}
								</div>

								{#if canEdit}
									<div
										class="flex flex-row gap-0.5 self-center opacity-0 group-hover:opacity-100 transition-opacity"
									>
										{#if shiftKey}
											<Tooltip content={$i18n.t('Delete')}>
												<button
													class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
													type="button"
													aria-label={$i18n.t('Delete')}
													on:click={() => {
														selectedTool = tool;
														showDeleteConfirm = true;
													}}
												>
													<GarbageBin />
												</button>
											</Tooltip>
										{:else}
											<ToolMenu
												editHandler={() => {
													goto(`/workspace/tools/edit?id=${encodeURIComponent(tool.id)}`);
												}}
												shareHandler={() => {}}
												cloneHandler={() => cloneHandler(tool)}
												exportHandler={() => exportHandler(tool)}
												deleteHandler={async () => {
													selectedTool = tool;
													showDeleteConfirm = true;
												}}
												onClose={() => {}}
											>
												<button
													class="self-center w-fit text-sm p-1.5 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
													type="button"
												>
													<EllipsisHorizontal className="size-5" />
												</button>
											</ToolMenu>
										{/if}
									</div>
								{/if}
							</div>
						{/each}
					</div>

					{#if toolsTotal && toolsTotal > 30}
						<div class="flex justify-center mt-4 mb-2">
							<Pagination bind:page={toolsPage} count={toolsTotal} perPage={30} />
						</div>
					{/if}
				</div>
			{:else}
				<div class="w-full flex flex-col justify-center items-center py-20 flex-1">
					<div class="max-w-sm text-center">
						<div
							class="flex items-center justify-center w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-800 mx-auto mb-4"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="1.5"
								stroke="currentColor"
								class="size-8 text-gray-400"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z"
								/>
							</svg>
						</div>
						<div class="text-base font-semibold mb-1.5">
							{$i18n.t('No tools in this category')}
						</div>
					</div>
				</div>
			{/if}
		</div>
	</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner className="size-5" />
	</div>
{/if}
