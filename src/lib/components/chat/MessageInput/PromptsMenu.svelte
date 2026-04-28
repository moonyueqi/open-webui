<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { getContext } from 'svelte';
	import { flyAndScale } from '$lib/utils/transitions';

	import { getPromptCategories, getPromptsByCategoryId } from '$lib/apis/prompt-categories';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import ChatBubbleOval from '$lib/components/icons/ChatBubbleOval.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';

	const i18n = getContext('i18n');

	export let onSelect: (content: string) => void = () => {};

	let show = false;
	let loading = false;

	let categories: any[] = [];

	let expandedCategoryId: string | null = null;
	let categoryPrompts: any[] | null = null;
	let categoryPromptsLoading = false;

	$: if (show) {
		loadData();
	}

	async function loadData() {
		if (categories.length > 0) return;
		loading = true;
		try {
			const catRes = await getPromptCategories(localStorage.token).catch(() => null);
			if (catRes?.items) {
				categories = catRes.items;
			}
		} catch {
			categories = [];
		}
		loading = false;
	}

	async function toggleCategory(categoryId: string) {
		if (expandedCategoryId === categoryId) {
			expandedCategoryId = null;
			categoryPrompts = null;
			return;
		}

		expandedCategoryId = categoryId;
		categoryPrompts = null;
		categoryPromptsLoading = true;

		try {
			const res = await getPromptsByCategoryId(localStorage.token, categoryId);
			if (res?.items) {
				categoryPrompts = res.items;
			} else {
				categoryPrompts = [];
			}
		} catch {
			categoryPrompts = [];
		}
		categoryPromptsLoading = false;
	}

	function handleSelect(content: string) {
		show = false;
		expandedCategoryId = null;
		categoryPrompts = null;
		onSelect(content);
	}
</script>

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			expandedCategoryId = null;
			categoryPrompts = null;
		}
	}}
>
	<Tooltip content={$i18n.t('Prompts')} placement="top">
		<button
			type="button"
			class="flex gap-1 items-center px-2.5 h-8 text-sm rounded-full transition-colors duration-200 outline-hidden focus:outline-hidden text-gray-700 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-800"
		>
			<ChatBubbleOval className="size-4" strokeWidth="1.75" />
			<span class="text-xs font-medium whitespace-nowrap">{$i18n.t('Prompts')}</span>
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
			{#if loading}
				<div class="flex items-center justify-center py-6 text-sm text-gray-500">
					<Spinner className="size-4" />
				</div>
			{:else}
				<div class="overflow-y-auto max-h-72 py-0.5">
					{#if categories.length === 0}
						<div class="px-3 py-4 text-center text-sm text-gray-500">
							{$i18n.t('No prompts found')}
						</div>
					{:else}
						{#each categories as category (category.id)}
							<div
								class="px-2.5 py-1.5 rounded-xl w-full text-left flex justify-between items-center text-sm hover:bg-gray-50 dark:hover:bg-gray-800/50"
							>
								<button
									class="w-full flex-1 flex items-center gap-1.5"
									type="button"
									on:click={() => toggleCategory(category.id)}
								>
									<div class="shrink-0">
										{#if expandedCategoryId === category.id}
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
										class="size-4 text-violet-500 shrink-0"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z"
										/>
									</svg>

									<Tooltip
										content={category.description || category.name}
										placement="top-start"
										className="flex flex-1 min-w-0"
									>
										<div class="line-clamp-1 flex-1 text-sm font-medium">
											{category.name}
										</div>
									</Tooltip>
								</button>
							</div>

							{#if expandedCategoryId === category.id}
								<div class="pl-6 mb-1 flex flex-col gap-0.5">
									{#if categoryPromptsLoading}
										<div class="py-1.5 flex justify-center">
											<Spinner className="size-3" />
										</div>
									{:else if categoryPrompts && categoryPrompts.length === 0}
										<div
											class="text-xs text-gray-500 dark:text-gray-400 italic py-1 px-2"
										>
											{$i18n.t('No prompts in this category')}
										</div>
									{:else if categoryPrompts}
										{#each categoryPrompts as promptItem (promptItem.id)}
											<Tooltip
												content={promptItem.content || ''}
												placement="right"
											>
												<button
													class="flex w-full items-center gap-2 px-2.5 py-1.5 text-sm cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50 text-left"
													type="button"
													on:click={() => handleSelect(promptItem.content)}
												>
													<svg
														xmlns="http://www.w3.org/2000/svg"
														fill="none"
														viewBox="0 0 24 24"
														stroke-width="1.5"
														stroke="currentColor"
														class="size-3.5 text-gray-400 shrink-0"
													>
														<path
															stroke-linecap="round"
															stroke-linejoin="round"
															d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
														/>
													</svg>
													<div class="flex-1 min-w-0">
														<div
															class="text-xs text-gray-700 dark:text-gray-300 truncate"
														>
															{promptItem.content}
														</div>
													</div>
												</button>
											</Tooltip>
										{/each}
									{/if}
								</div>
							{/if}
						{/each}
					{/if}
				</div>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
