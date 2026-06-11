<script lang="ts">
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { toast } from 'svelte-sonner';

	import { goto, afterNavigate } from '$app/navigation';
	import { onMount, getContext } from 'svelte';
	import { WEBUI_NAME, user } from '$lib/stores';

	import {
		getToolCategories,
		deleteToolCategoryById
	} from '$lib/apis/tool-categories';
	import { capitalizeFirstLetter } from '$lib/utils';

	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Search from '../icons/Search.svelte';
	import Plus from '../icons/Plus.svelte';
	import Spinner from '../common/Spinner.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import XMark from '../icons/XMark.svelte';
	import GarbageBin from '../icons/GarbageBin.svelte';
	import Badge from '$lib/components/common/Badge.svelte';
	import Pagination from '../common/Pagination.svelte';

	let shiftKey = false;
	const i18n = getContext('i18n');
	let loaded = false;

	let query = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;

	let categories: any[] | null = null;
	let total: number | null = null;
	let loading = false;

	let showDeleteConfirm = false;
	let deleteCategory: any = null;

	let page = 1;

	$: if (loaded && query !== undefined) {
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			page = 1;
			getCategoryList();
		}, 300);
	}

	$: if (loaded && page) {
		getCategoryList();
	}

	const getCategoryList = async () => {
		loading = true;
		try {
			const res = await getToolCategories(localStorage.token, page, '', query).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);

			if (res) {
				categories = res.items;
				total = res.total;
			} else {
				categories = [];
				total = 0;
			}
		} catch (err) {
			console.error(err);
			categories = [];
			total = 0;
		} finally {
			loading = false;
		}
	};

	const deleteHandler = async (category: any) => {
		const res = await deleteToolCategoryById(localStorage.token, category.id).catch((err) => {
			toast.error(`${err}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Deleted {{name}}', { name: category.name }));
		}

		page = 1;
		getCategoryList();
	};

	afterNavigate(() => {
		if (loaded) {
			getCategoryList();
		}
	});

	onMount(async () => {
		loaded = true;
		await getCategoryList();

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

<svelte:head>
	<title>
		{$i18n.t('Tools')} • {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<DeleteConfirmDialog
		bind:show={showDeleteConfirm}
		title={$i18n.t('Delete category?')}
		on:confirm={() => {
			deleteHandler(deleteCategory);
		}}
	>
		<div class="text-sm text-gray-500 truncate">
			{$i18n.t('This will delete')} <span class="font-medium">{deleteCategory?.name}</span>.
		</div>
		<div class="text-xs text-red-500 mt-2">
			{$i18n.t('All tools under this category will also be deleted.')}
		</div>
	</DeleteConfirmDialog>

	<div class="flex flex-col h-full min-h-0 overflow-hidden">
		<div class="flex flex-col gap-2 px-1 mt-1.5 mb-4 shrink-0">
			<div class="flex justify-between items-center">
				<div class="flex items-center gap-3 shrink-0">
					<div
						class="flex items-center justify-center w-9 h-9 rounded-xl bg-sky-500/10 dark:bg-sky-500/15"
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
					<div>
						<div class="text-xl font-semibold">{$i18n.t('Tools')}</div>
						{#if total !== null}
							<div class="text-xs text-gray-500 dark:text-gray-400">
								{total}
								{$i18n.t('categories')}
							</div>
						{/if}
					</div>
				</div>

				<div class="flex w-full justify-end gap-1.5">
					{#if $user?.role === 'admin'}
						<a
							class="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
							href="/workspace/tools/categories/create"
						>
							<Plus className="size-3.5" strokeWidth="2.5" />
							<div class="hidden md:block text-xs">{$i18n.t('New Category')}</div>
						</a>
					{/if}
				</div>
			</div>
		</div>

		<div
			class="py-2.5 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm min-h-0 flex flex-col overflow-hidden"
			style="flex: 1 1 0; max-height: calc(100% - 7rem);"
		>
			<div class="flex w-full space-x-2 py-0.5 px-4 pb-2.5 shrink-0">
				<div
					class="flex flex-1 items-center bg-gray-50 dark:bg-gray-850 rounded-xl px-3 py-1.5 transition focus-within:ring-2 focus-within:ring-gray-300/50 dark:focus-within:ring-gray-600/50 focus-within:bg-white dark:focus-within:bg-gray-900"
				>
					<Search className="size-3.5 text-gray-400 shrink-0" />
					<input
						class="w-full text-sm py-0.5 pl-2 outline-hidden bg-transparent placeholder:text-gray-400"
						bind:value={query}
						aria-label={$i18n.t('Search Categories')}
						placeholder={$i18n.t('Search Categories')}
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

			{#if categories === null || loading}
				<div class="w-full flex justify-center items-center py-16 flex-1">
					<Spinner className="size-5" />
				</div>
			{:else if (categories ?? []).length !== 0}
				<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden mt-2 px-3">
					<div class="gap-2.5 grid lg:grid-cols-2">
						{#each categories as category (category.id)}
							<a
								class="group flex text-left w-full px-4 py-3.5 hover:bg-gray-50 dark:hover:bg-gray-850/60 transition-all duration-200 rounded-xl border border-transparent hover:border-gray-200/60 dark:hover:border-gray-700/40 hover:shadow-sm"
								href={`/workspace/tools/categories/${category.id}`}
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
									<div class="flex-1 min-w-0">
										<div class="flex items-center justify-between w-full mb-1">
											<div class="flex items-center gap-2 min-w-0">
												<Tooltip content={category?.description ?? category.name}>
													<div class="font-semibold text-sm line-clamp-1">{category.name}</div>
												</Tooltip>
											</div>
											{#if !category.write_access}
												<Badge type="muted" content={$i18n.t('Read Only')} />
											{/if}
										</div>

										<div
											class="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mb-1.5"
										>
											{#if category?.user?.name}
												<Tooltip
													content={category?.user?.email ?? $i18n.t('Deleted User')}
													className="flex shrink-0"
													placement="top-start"
												>
													<span class="shrink-0">
														{$i18n.t('By {{name}}', {
															name: capitalizeFirstLetter(
																category?.user?.name ??
																	category?.user?.email ??
																	$i18n.t('Deleted User')
															)
														})}
													</span>
												</Tooltip>
											{/if}

											{#if category.updated_at}
												<span class="text-gray-300 dark:text-gray-600">·</span>
												<Tooltip content={dayjs(category.updated_at * 1000).format('LLLL')}>
													<span class="shrink-0">
														{$i18n.t('Updated')}
														{dayjs(category.updated_at * 1000).fromNow()}
													</span>
												</Tooltip>
											{/if}

											<span class="text-gray-300 dark:text-gray-600">·</span>
											<span class="shrink-0">
												{$i18n.t('{{count}} tool(s)', { count: category.tool_count ?? 0 })}
											</span>
										</div>
									</div>
								</div>
								{#if $user?.role === 'admin'}
									<div
										class="flex flex-row gap-0.5 self-center opacity-0 group-hover:opacity-100 transition-opacity"
									>
										<Tooltip content={$i18n.t('Delete')}>
											<button
												class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
												type="button"
												aria-label={$i18n.t('Delete')}
												on:click|preventDefault|stopPropagation={() => {
													deleteCategory = category;
													showDeleteConfirm = true;
												}}
											>
												<GarbageBin />
											</button>
										</Tooltip>
									</div>
								{/if}
							</a>
						{/each}
					</div>

					{#if total && total > 30}
						<div class="flex justify-center mt-4 mb-2">
							<Pagination bind:page count={total} perPage={30} />
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
							{$i18n.t('No categories found')}
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
