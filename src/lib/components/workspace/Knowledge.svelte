<script lang="ts">
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { toast } from 'svelte-sonner';
	import { onMount, getContext, tick, onDestroy } from 'svelte';
	const i18n = getContext('i18n');

	import { WEBUI_NAME, knowledge, user } from '$lib/stores';
	import {
		deleteKnowledgeById,
		searchKnowledgeBases,
		exportKnowledgeById
	} from '$lib/apis/knowledge';

	import { goto } from '$app/navigation';
	import { capitalizeFirstLetter } from '$lib/utils';

	import DeleteConfirmDialog from '../common/ConfirmDialog.svelte';
	import ItemMenu from './Knowledge/ItemMenu.svelte';
	import Badge from '../common/Badge.svelte';
	import Search from '../icons/Search.svelte';
	import Plus from '../icons/Plus.svelte';
	import Spinner from '../common/Spinner.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import XMark from '../icons/XMark.svelte';
	import ViewSelector from './common/ViewSelector.svelte';
	import Loader from '../common/Loader.svelte';

	let loaded = false;
	let showDeleteConfirm = false;
	let tagsContainerElement: HTMLDivElement;

	let selectedItem = null;

	let page = 1;
	let query = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;
	let viewOption = '';

	let items = null;
	let total = null;

	let allItemsLoaded = false;
	let itemsLoading = false;

	$: if (query !== undefined) {
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			init();
		}, 300);
	}

	onDestroy(() => {
		clearTimeout(searchDebounceTimer);
	});

	$: if (viewOption !== undefined) {
		init();
	}

	const reset = () => {
		page = 1;
		items = null;
		total = null;
		allItemsLoaded = false;
		itemsLoading = false;
	};

	const loadMoreItems = async () => {
		if (allItemsLoaded) return;
		page += 1;
		await getItemsPage();
	};

	const init = async () => {
		if (!loaded) return;

		reset();
		await getItemsPage();
	};

	const getItemsPage = async () => {
		itemsLoading = true;
		const res = await searchKnowledgeBases(localStorage.token, query, viewOption, page).catch(
			() => {
				return [];
			}
		);

		if (res) {
			console.log(res);
			total = res.total;
			const pageItems = res.items;

			if ((pageItems ?? []).length === 0) {
				allItemsLoaded = true;
			} else {
				allItemsLoaded = false;
			}

			if (items) {
				items = [...items, ...pageItems];
			} else {
				items = pageItems;
			}
		}

		itemsLoading = false;
		return res;
	};

	const deleteHandler = async (item) => {
		const res = await deleteKnowledgeById(localStorage.token, item.id).catch((e) => {
			toast.error(`${e}`);
		});

		if (res) {
			toast.success($i18n.t('Knowledge deleted successfully.'));
			init();
		}
	};

	const exportHandler = async (item) => {
		try {
			const blob = await exportKnowledgeById(localStorage.token, item.id);
			if (blob) {
				const url = URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url;
				a.download = `${item.name}.zip`;
				document.body.appendChild(a);
				a.click();
				document.body.removeChild(a);
				URL.revokeObjectURL(url);
			}
		} catch (e) {
			toast.error(`${e}`);
		}
	};

	onMount(async () => {
		viewOption = localStorage?.workspaceViewOption || '';
		loaded = true;
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Knowledge')} • {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<DeleteConfirmDialog
		bind:show={showDeleteConfirm}
		on:confirm={() => {
			deleteHandler(selectedItem);
		}}
	/>

	<div class="flex flex-col h-full min-h-0 overflow-hidden">
		<div class="flex flex-col gap-2 px-1 mt-1.5 mb-4 shrink-0">
			<div class="flex justify-between items-center">
				<div class="flex items-center gap-3 shrink-0">
					<div class="flex items-center justify-center w-9 h-9 rounded-xl bg-emerald-500/10 dark:bg-emerald-500/15">
						<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5 text-emerald-600 dark:text-emerald-400">
							<path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
						</svg>
					</div>
					<div>
						<div class="text-xl font-semibold">{$i18n.t('Knowledge')}</div>
						{#if total !== null}
							<div class="text-xs text-gray-500 dark:text-gray-400">{total} 项</div>
						{/if}
					</div>
				</div>

				<div class="flex w-full justify-end gap-1.5">
					<a
						class="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
						href="/workspace/knowledge/preprocess"
					>
						<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-3.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" />
						</svg>
						<div class="hidden md:block text-xs">{$i18n.t('Preprocess')}</div>
					</a>
					<a
						class="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
						href="/workspace/knowledge/create"
					>
						<Plus className="size-3.5" strokeWidth="2.5" />
						<div class="hidden md:block text-xs">{$i18n.t('New Knowledge')}</div>
					</a>
				</div>
			</div>
		</div>

		<div
			class="py-2.5 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm min-h-0 flex flex-col overflow-hidden"
			style="flex: 1 1 0; max-height: calc(100% - 7rem);"
		>
			<div class="flex w-full space-x-2 py-0.5 px-4 pb-2.5 shrink-0">
				<div class="flex flex-1 items-center bg-gray-50 dark:bg-gray-850 rounded-xl px-3 py-1.5 transition focus-within:ring-2 focus-within:ring-gray-300/50 dark:focus-within:ring-gray-600/50 focus-within:bg-white dark:focus-within:bg-gray-900">
					<Search className="size-3.5 text-gray-400 shrink-0" />
					<input
						class="w-full text-sm py-0.5 pl-2 outline-hidden bg-transparent placeholder:text-gray-400"
						bind:value={query}
						aria-label={$i18n.t('Search Knowledge')}
						placeholder={$i18n.t('Search Knowledge')}
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
					bind:this={tagsContainerElement}
				>
					<ViewSelector
						bind:value={viewOption}
						onChange={async (value) => {
							localStorage.workspaceViewOption = value;
							await tick();
						}}
					/>
				</div>
			</div>

			{#if items !== null && total !== null}
				{#if (items ?? []).length !== 0}
					<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden mt-2 px-3">
						<div class="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
							{#each items as item}
								<button
									class="group flex text-left w-full px-4 py-3.5 hover:bg-gray-50 dark:hover:bg-gray-850/60 transition-all duration-200 rounded-xl border border-transparent hover:border-gray-200/60 dark:hover:border-gray-700/40 hover:shadow-sm"
									on:click={() => {
										if (item?.meta?.document) {
											toast.error(
												$i18n.t(
													'Only collections can be edited, create a new knowledge base to edit/add documents.'
												)
											);
										} else {
											goto(`/workspace/knowledge/${item.id}`);
										}
									}}
								>
									<div class="flex items-start gap-3 flex-1 min-w-0">
										<div class="flex items-center justify-center w-10 h-10 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 shrink-0 mt-0.5 group-hover:bg-emerald-100 dark:group-hover:bg-emerald-500/20 transition-colors">
											<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5 text-emerald-600 dark:text-emerald-400">
												<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z" />
											</svg>
										</div>
										<div class="flex-1 min-w-0">
											<div class="flex items-center justify-between gap-2 mb-1">
												<Tooltip content={item?.description ?? item.name} placement="top-start">
													<div class="text-sm font-semibold line-clamp-1 capitalize">{item.name}</div>
												</Tooltip>
												{#if !item?.write_access}
													<Badge type="muted" content={$i18n.t('Read Only')} />
												{/if}
											</div>

											<div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
												<Tooltip
													content={item?.user?.email ?? $i18n.t('Deleted User')}
													className="flex shrink-0"
													placement="top-start"
												>
													<span>{$i18n.t('By {{name}}', {
														name: capitalizeFirstLetter(
															item?.user?.name ?? item?.user?.email ?? $i18n.t('Deleted User')
														)
													})}</span>
												</Tooltip>
												<span class="text-gray-300 dark:text-gray-600">·</span>
												<Tooltip content={dayjs(item.updated_at * 1000).format('LLLL')}>
													<span class="shrink-0">
														{$i18n.t('Updated')} {dayjs(item.updated_at * 1000).fromNow()}
													</span>
												</Tooltip>
												{#if item.file_count != null}
													<span class="text-gray-300 dark:text-gray-600">·</span>
													<span class="shrink-0">{$i18n.t('{{count}} file(s)', { count: item.file_count ?? 0 })}</span>
												{/if}
											</div>
										</div>
									</div>
									{#if item?.write_access || $user?.role === 'admin'}
										<div class="flex flex-row gap-0.5 self-center opacity-0 group-hover:opacity-100 transition-opacity">
											<ItemMenu
												onExport={$user.role === 'admin'
													? () => {
															exportHandler(item);
														}
													: null}
												on:delete={() => {
													selectedItem = item;
													showDeleteConfirm = true;
												}}
											/>
										</div>
									{/if}
								</button>
							{/each}
						</div>

						{#if !allItemsLoaded}
						<Loader
							on:visible={(e) => {
								if (!itemsLoading) {
									loadMoreItems();
								}
							}}
						>
							<div class="w-full flex justify-center py-5 text-xs animate-pulse items-center gap-2 text-gray-400">
								<Spinner className="size-4" />
								<div>{$i18n.t('Loading...')}</div>
							</div>
						</Loader>
					{/if}
				</div>
			{:else}
				<div class="w-full flex flex-col justify-center items-center py-20 flex-1">
					<div class="max-w-sm text-center">
						<div class="flex items-center justify-center w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-800 mx-auto mb-4">
							<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-8 text-gray-400">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
							</svg>
						</div>
						<div class="text-base font-semibold mb-1.5">{$i18n.t('No knowledge found')}</div>
					</div>
				</div>
			{/if}
		{:else}
			<div class="w-full flex justify-center items-center py-16 flex-1">
				<Spinner className="size-5" />
			</div>
		{/if}

	</div>

	<div class="flex items-center gap-1.5 text-gray-400 dark:text-gray-500 text-xs mt-2 mb-1 ml-1 shrink-0">
		<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-3.5 shrink-0">
			<path stroke-linecap="round" stroke-linejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
		</svg>
		{$i18n.t("Use '#' in the prompt input to load and include your knowledge.")}
	</div>
</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner className="size-5" />
	</div>
{/if}
