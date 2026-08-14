<script lang="ts">
	import { onMount, tick, getContext } from 'svelte';
	import { goto } from '$app/navigation';

	import Textarea from '$lib/components/common/Textarea.svelte';
	import { toast } from 'svelte-sonner';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import Clipboard from '$lib/components/icons/Clipboard.svelte';
	import Check from '$lib/components/icons/Check.svelte';
	import AccessControlModal from '../common/AccessControlModal.svelte';
	import { user } from '$lib/stores';
	import { slugify, formatDate, copyToClipboard, validateInputVariables } from '$lib/utils';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte';
	import {
		getPromptHistory,
		setProductionPromptVersion,
		deletePromptHistoryVersion,
		updatePromptMetadata,
		updatePromptAccessGrants,
		getPromptTags
	} from '$lib/apis/prompts';
	import { page } from '$app/stores';
	import dayjs from 'dayjs';
	import localizedFormat from 'dayjs/plugin/localizedFormat';
	import PromptHistoryMenu from './PromptHistoryMenu.svelte';
	import Badge from '$lib/components/common/Badge.svelte';
	import Tags from '$lib/components/common/Tags.svelte';

	dayjs.extend(localizedFormat);

	export let onSubmit: Function;
	export let edit = false;
	export let prompt = null;
	export let clone = false;
	export let disabled = false;

	const i18n = getContext('i18n');

	let loading = false;
	let showEditModal = false;

	let name = '';
	let command = '';
	let content = '';
	let tags = [];
	let commitMessage = '';
	let isProduction = true;
	let categoryId: string | null = null;

	let accessGrants = [];
	let showAccessControlModal = false;
	let hasManualEdit = false;

	let history: any[] = [];
	let historyLoading = false;
	let selectedHistoryEntry: any = null;
	let historyPage = 0;
	let historyHasMore = true;
	let contentCopied = false;

	// For debounced auto-save of name/command
	let originalName = '';
	let originalCommand = '';
	let originalTags = [];
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	let suggestionTags = [];

	$: if (!edit && !hasManualEdit) {
		command = name !== '' ? slugify(name) : '';
	}

	function handleCommandInput(e: Event) {
		hasManualEdit = true;
	}

	const showVariableIssues = (): boolean => {
		const issues = validateInputVariables(content);
		let hasError = false;
		for (const issue of issues) {
			const message = $i18n.t(issue.key, issue.params ?? {});
			if (issue.severity === 'error') {
				toast.error(message);
				hasError = true;
			} else {
				toast.warning(message);
			}
		}
		// Errors block submission; warnings are informational only.
		return !hasError;
	};

	const submitHandler = async () => {
		if (disabled) {
			toast.error($i18n.t('You do not have permission to edit this prompt.'));
			return;
		}

		if (!showVariableIssues()) {
			return;
		}

		loading = true;

		if (edit) {
			if (validateCommandString(command)) {
				await onSubmit({
					id: prompt?.id,
					name,
					command,
					content,
					tags: tags.map((tag) => tag.name),
					access_grants: accessGrants,
					commit_message: commitMessage || undefined,
					is_production: isProduction,
					category_id: categoryId
				});
				showEditModal = false;
				commitMessage = '';
				isProduction = true;
				await loadHistory(true);
				if (history.length > 0) {
					selectedHistoryEntry = history[0];
				}
			} else {
				toast.error(
					$i18n.t('Only alphanumeric characters and hyphens are allowed in the command string.')
				);
			}
		} else {
			await onSubmit({
				content,
				category_id: categoryId
			});
		}

		loading = false;
	};

	const validateCommandString = (inputString) => {
		const regex = /^[a-zA-Z0-9-_]+$/;
		return regex.test(inputString);
	};

	const loadHistory = async (reset = false) => {
		if (!prompt?.id || !edit) return;
		if (historyLoading) return;
		if (!reset && !historyHasMore) return;

		historyLoading = true;

		if (reset) {
			historyPage = 0;
			historyHasMore = true;
		}

		try {
			const newEntries = await getPromptHistory(localStorage.token, prompt.id, historyPage);

			if (reset) {
				history = newEntries;
			} else {
				history = [...history, ...newEntries];
			}

			historyHasMore = newEntries.length > 0;
			historyPage = historyPage + 1;
		} catch (error) {
			console.error('Failed to load history:', error);
			if (reset) {
				history = [];
			}
		}
		historyLoading = false;
	};

	const handleHistoryScroll = (e: Event) => {
		const target = e.target as HTMLElement;
		const nearBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + 50;
		if (nearBottom && historyHasMore && !historyLoading) {
			loadHistory(false);
		}
	};

	const copyContent = async () => {
		const textToCopy = selectedHistoryEntry?.snapshot?.content || content;
		const success = await copyToClipboard(textToCopy);
		if (success) {
			contentCopied = true;
			setTimeout(() => {
				contentCopied = false;
			}, 2000);
		}
	};

	const setAsProduction = async (historyEntry: any) => {
		if (disabled) {
			toast.error($i18n.t('You do not have permission to edit this prompt.'));
			return;
		}

		try {
			await setProductionPromptVersion(localStorage.token, prompt.id, historyEntry.id);
			// Update local prompt object to trigger reactivity
			prompt = { ...prompt, version_id: historyEntry.id };
			toast.success($i18n.t('Production version updated'));
		} catch (error) {
			toast.error(`${error}`);
		}
	};

	const handleDeleteHistory = async (historyId: string) => {
		if (disabled) return;

		try {
			await deletePromptHistoryVersion(localStorage.token, prompt.id, historyId);
			toast.success($i18n.t('Version deleted'));
			// Reload history from scratch
			await loadHistory(true);
			// Reset selection if deleted entry was selected
			if (selectedHistoryEntry?.id === historyId) {
				selectedHistoryEntry = history.length > 0 ? history[0] : null;
			}
		} catch (error) {
			toast.error(`${error}`);
		}
	};

	const renderDate = (timestamp: number) => {
		const dateVal = timestamp * 1000;
		return $i18n.t(formatDate(dateVal), {
			LOCALIZED_TIME: dayjs(dateVal).format('LT'),
			LOCALIZED_DATE: dayjs(dateVal).format('L')
		});
	};

	const debouncedSaveMetadata = () => {
		if (disabled || !edit) return;

		if (debounceTimer) {
			clearTimeout(debounceTimer);
		}

		debounceTimer = setTimeout(async () => {
			if (!validateCommandString(command)) {
				toast.error(
					$i18n.t('Only alphanumeric characters and hyphens are allowed in the command string.')
				);
				command = originalCommand;
				return;
			}

			try {
				await updatePromptMetadata(
					localStorage.token,
					prompt?.id,
					name,
					command,
					tags.map((tag) => tag.name)
				);
				// Update originals on success
				originalName = name;
				originalCommand = command;
				originalTags = tags;
				toast.success($i18n.t('Saved'));
			} catch (error) {
				toast.error(`${error}`);
				// Revert on error (collision)
				name = originalName;
				command = originalCommand;
				tags = originalTags;
			}
		}, 500);
	};

	onMount(async () => {
		if (prompt) {
			name = prompt.name || '';
			await tick();
			command = prompt.command.at(0) === '/' ? prompt.command.slice(1) : prompt.command;
			content = prompt.content;
			tags = (prompt.tags || []).map((tag) => ({ name: tag }));
			accessGrants = prompt?.access_grants === undefined ? [] : prompt?.access_grants;
			categoryId = prompt.category_id || null;

			originalName = name;
			originalCommand = command;
			originalTags = tags;

			if (edit) {
				await loadHistory();
				if (prompt.version_id && history.length > 0) {
					selectedHistoryEntry = history.find((h) => h.id === prompt.version_id) || history[0];
				} else if (history.length > 0) {
					selectedHistoryEntry = history[0];
				}
			}
		}

		if (!edit) {
			const urlCategoryId = $page.url.searchParams.get('category_id');
			if (urlCategoryId) {
				categoryId = urlCategoryId;
			}
		}

		if (edit) {
			const res = await getPromptTags(localStorage.token);
			if (res) {
				suggestionTags = res.map((tag) => ({ name: tag }));
			}
		}
	});
</script>

<AccessControlModal
	bind:show={showAccessControlModal}
	bind:accessGrants
	accessRoles={['read', 'write']}
	share={$user?.permissions?.sharing?.prompts || $user?.role === 'admin'}
	sharePublic={$user?.permissions?.sharing?.public_prompts || $user?.role === 'admin'}
	shareUsers={($user?.permissions?.access_grants?.allow_users ?? true) || $user?.role === 'admin'}
	onChange={async () => {
		if (edit && prompt?.id) {
			try {
				await updatePromptAccessGrants(localStorage.token, prompt.id, accessGrants);
				toast.success($i18n.t('Saved'));
			} catch (error) {
				toast.error(`${error}`);
			}
		}
	}}
/>

<!-- Edit Modal -->
<Modal size="lg" bind:show={showEditModal}>
	<div class="px-5 pt-4 pb-5">
		<div class="flex justify-between items-center mb-2">
			<div class="text-lg font-medium">{$i18n.t('Edit Prompt')}</div>
			<button
				class="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
				aria-label={$i18n.t('Close')}
				on:click={() => (showEditModal = false)}
			>
				<XMark className="size-5" />
			</button>
		</div>

		<form on:submit|preventDefault={submitHandler}>
			<div class="my-2">
				<div class="flex w-full justify-between">
					<div class="text-gray-500 text-xs">{$i18n.t('Prompt Content')}</div>
				</div>

				<div class="mt-1">
					<Textarea
					className="text-sm w-full bg-transparent outline-hidden overflow-y-hidden resize-none"
					placeholder={$i18n.t('Enter the prompt content that the AI will follow to generate a response...')}
					bind:value={content}
					aria-label={$i18n.t('Prompt Content')}
					rows={6}
					required
				/>
				</div>

				<div
					class="mt-1 flex items-start gap-1 text-[11px] leading-relaxed text-gray-400 dark:text-gray-500"
				>
					<InfoCircle className="size-3 shrink-0 mt-0.5" />
					<span>
						{@html $i18n.t(
							'Tip: use <code>&#123;&#123;name&#125;&#125;</code> for a text input, or <code>&#123;&#123;name：option1、option2、option3&#125;&#125;</code> for a dropdown single-select.'
						)}
					</span>
				</div>
			</div>

			<div class="my-2">
				<div class="text-gray-500 text-xs">{$i18n.t('Commit Message')} ({$i18n.t('optional')})</div>
				<div class="mt-1">
					<input
						class="text-sm w-full bg-transparent outline-hidden"
						placeholder={$i18n.t('Describe what changed...')}
						aria-label={$i18n.t('Commit Message')}
						bind:value={commitMessage}
					/>
				</div>
			</div>

			<div class="mt-4 flex items-center justify-between">
				<label class="flex items-center gap-2 cursor-pointer">
					<input
						type="checkbox"
						bind:checked={isProduction}
						class="w-4 h-4 rounded border-gray-300 dark:border-gray-600"
					/>
					<span class="text-sm text-gray-700 dark:text-gray-300"
						>{$i18n.t('Set as Production')}</span
					>
				</label>
				<div>
					<button
						class="text-sm px-4 py-2 transition rounded-full {loading || disabled
							? 'cursor-not-allowed bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
							: 'bg-black hover:bg-gray-900 text-white dark:bg-white dark:hover:bg-gray-100 dark:text-black'} flex justify-center"
						type="submit"
						disabled={loading || disabled}
					>
						<div class="font-medium">{$i18n.t('Save')}</div>
						{#if loading}
							<div class="ml-1.5">
								<Spinner />
							</div>
						{/if}
					</button>
				</div>
			</div>
		</form>
	</div>
</Modal>

{#if edit}
	<!-- Edit mode: Read-only view with history -->
	<div class="flex flex-col w-full h-full max-h-[100dvh]">
		<!-- Header -->
		<div class="flex items-start justify-between gap-4 shrink-0">
			<div class="min-w-0 flex-1">
				<input
					class="text-2xl w-full bg-transparent outline-hidden"
					placeholder={$i18n.t('Prompt Name')}
					bind:value={name}
					on:input={debouncedSaveMetadata}
					{disabled}
				/>

				<input type="hidden" bind:value={command} />
			</div>

			<div>
				<div class="flex items-center gap-2 shrink-0 justify-end">
					{#if !disabled}
						<button
							class="px-4 py-1 text-sm font-medium bg-black text-white dark:bg-white dark:text-black rounded-full hover:opacity-90 transition shadow-xs"
							on:click={() => (showEditModal = true)}
						>
							{$i18n.t('Edit')}
						</button>

						<button
							class="bg-gray-50 hover:bg-gray-100 text-black dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-white transition px-2.5 py-1 rounded-full flex gap-1.5 items-center text-sm border border-gray-100 dark:border-gray-800"
							on:click={() => (showAccessControlModal = true)}
						>
							<LockClosed strokeWidth="2.5" className="size-3.5" />
							{$i18n.t('Access')}
						</button>
					{:else}
						<span class="text-xs text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded-full"
							>{$i18n.t('Read Only')}</span
						>
					{/if}
				</div>

				<div class="mt-1.5">
					<Tooltip content={$i18n.t('Click to copy ID')}>
						<button
							class="text-xs text-gray-500 font-mono px-2 py-1 rounded-lg cursor-pointer hover:underline transition"
							on:click={() => {
								copyToClipboard(prompt.id);
								toast.success($i18n.t('ID copied to clipboard'));
							}}
						>
							{prompt.id}
						</button>
					</Tooltip>
				</div>
			</div>
		</div>

		<div class="mb-2 flex justify-between items-center gap-2">
			<div class="flex-1 min-w-0">
				<Tags
					{tags}
					{disabled}
					{suggestionTags}
					on:add={(e) => {
						tags = [...tags, { name: e.detail }];
						debouncedSaveMetadata();
					}}
					on:delete={(e) => {
						tags = tags.filter((tag) => tag.name !== e.detail);
						debouncedSaveMetadata();
					}}
				/>
			</div>
		</div>

		<div class="flex flex-col md:flex-row gap-4 flex-1 overflow-hidden pb-6">
			<!-- Desktop History Sidebar -->
			<div class="hidden md:flex md:flex-col w-72 shrink-0 overflow-hidden">
				<div class="flex-1 overflow-y-auto">
					{@render historySection()}
				</div>
			</div>

			<!-- Prompt Content -->
			<div class="flex-1 flex flex-col min-h-0 overflow-hidden">
				<div class="flex items-center justify-between mb-1 shrink-0">
					<div class="flex items-center gap-2">
						<div class="text-gray-500 text-xs">
							{$i18n.t('Prompt Content')}
						</div>
						{#if selectedHistoryEntry}
							<span
								class="text-xs text-gray-500 font-mono bg-gray-100 dark:bg-gray-800 px-1.5 rounded"
							>
								{selectedHistoryEntry.id.slice(0, 7)}
							</span>
						{/if}
					</div>

					{#if selectedHistoryEntry && !disabled}
						<div class="flex items-center gap-2">
							{#if selectedHistoryEntry.id === prompt?.version_id}
								<Badge type="success" content={$i18n.t('Live')} />
							{:else}
								<button
									class="text-xs text-gray-500 hover:text-gray-900 dark:hover:text-gray-300 hover:underline transition"
									on:click={() => setAsProduction(selectedHistoryEntry)}
								>
									{$i18n.t('Set as Production')}
								</button>
							{/if}
							<PromptHistoryMenu
								isProduction={selectedHistoryEntry.id === prompt?.version_id}
								onDelete={() => handleDeleteHistory(selectedHistoryEntry.id)}
								onClose={() => {}}
							/>
						</div>
					{/if}
				</div>
				<!-- Content container with copy button -->
				<div class="relative flex-1 min-h-0">
					<!-- Copy button - outside scroll area -->
					<div class="absolute top-2 right-2 z-10">
						<button
							class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
							aria-label={$i18n.t('Copy content')}
							on:click={copyContent}
						>
							{#if contentCopied}
								<Check className="size-4 text-green-500" />
							{:else}
								<Clipboard className="size-4 text-gray-500" />
							{/if}
						</button>
					</div>
					<!-- Scrollable content -->
					<div
						class="bg-gray-50 dark:bg-gray-900 rounded-xl px-4 py-3 border border-gray-100/50 dark:border-gray-850/50 h-full overflow-y-auto"
					>
						<pre class="text-xs whitespace-pre-wrap font-mono pr-8">{selectedHistoryEntry?.snapshot
								?.content || content}</pre>
					</div>
				</div>
			</div>
		</div>
	</div>
{:else}
	<!-- Create mode: Form -->
	<div class="w-full h-full overflow-y-auto scrollbar-hidden">
		<button
			class="flex items-center gap-1.5 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 transition"
			on:click={() => {
				if (categoryId) {
					goto(`/workspace/prompts/categories/${categoryId}`);
				} else {
					goto('/workspace/prompts');
				}
			}}
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
			<span class="font-medium text-sm">{$i18n.t('Back')}</span>
		</button>

		<form
			class="flex flex-col max-w-lg mx-auto mt-14 mb-10"
			on:submit|preventDefault={submitHandler}
		>
			<div class="w-full flex flex-col justify-center">
				<div class="flex items-center gap-2.5 mb-6">
					<div class="p-2 rounded-xl bg-gray-100 dark:bg-gray-800">
						<svg
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
							stroke-width="1.5"
							stroke="currentColor"
							class="w-6 h-6 text-gray-600 dark:text-gray-300"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
							/>
						</svg>
					</div>
					<div>
						<h1 class="text-xl font-semibold font-primary">
							{$i18n.t('Create a prompt')}
						</h1>
					</div>
				</div>

				<div class="w-full flex flex-col gap-4">
					<div class="w-full">
						<label for="prompt-content" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
							{$i18n.t('Prompt Content')} <span class="text-red-500">*</span>
						</label>
				<textarea
					class="w-full rounded-xl py-2.5 px-4 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-300 outline-hidden border border-gray-800 dark:border-gray-300 focus:border-black dark:focus:border-white focus:ring-0 transition placeholder:text-gray-400 dark:placeholder:text-gray-500 overflow-y-auto scrollbar-thin"
					placeholder={$i18n.t('Enter the prompt content that the AI will follow to generate a response...')}
					bind:value={content}
					rows="6"
					style="max-height: 300px;"
					required
				></textarea>

						<div
							class="mt-1 flex items-start gap-1 text-[11px] leading-relaxed text-gray-400 dark:text-gray-500"
						>
							<InfoCircle className="size-3 shrink-0 mt-0.5" />
							<span>
								{@html $i18n.t(
									'Tip: use <code>&#123;&#123;name&#125;&#125;</code> for a text input, or <code>&#123;&#123;name：option1、option2、option3&#125;&#125;</code> for a dropdown single-select.'
								)}
							</span>
						</div>
					</div>
				</div>
			</div>

			<div class="flex justify-end mt-5">
				<button
					class="px-3.5 py-1.5 text-xs font-medium transition rounded-lg flex items-center gap-1.5 {loading
						? 'cursor-not-allowed bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500'
						: 'bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100'}"
					type="submit"
					disabled={loading}
				>
					{#if loading}
						<Spinner className="size-4" />
					{/if}
					{$i18n.t('Save & Create')}
				</button>
			</div>
		</form>
	</div>
{/if}

{#snippet historySection()}
	<div class="flex flex-col h-full">
		<div class="flex items-center justify-between mb-2 shrink-0">
			<div class="text-gray-500 text-xs">{$i18n.t('History')}</div>
		</div>

		{#if history.length > 0}
			<div class="space-y-0 flex-1 overflow-y-auto" on:scroll={handleHistoryScroll}>
				{#each history as entry, index}
					<div class="flex">
						<!-- Content -->
						<button
							class="flex-1 text-left px-3.5 py-2 mb-1 rounded-2xl transition group
								{selectedHistoryEntry?.id === entry.id
								? 'bg-gray-100/50 dark:bg-gray-850/50'
								: 'hover:bg-gray-100/50 dark:hover:bg-gray-850/50'}"
							on:click={() => (selectedHistoryEntry = entry)}
						>
							<!-- Commit Message -->
							<div class="flex items-center gap-2 mb-1">
								<div class="text-xs text-gray-900 dark:text-white truncate">
									{entry.commit_message || $i18n.t('Update')}
								</div>
								{#if entry.id === prompt?.version_id}
									<Badge type="success" content={$i18n.t('Live')} />
								{/if}
							</div>

							<!-- User + Time -->
							<div class="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
								{#if entry.user}
									<img
										src={`/api/v1/users/${entry.user.id}/profile/image`}
										alt={entry.user.name}
										class="size-3 rounded-full mr-0.5"
										on:error={(e) => (e.target.src = '/user.png')}
									/>
									<span class="truncate">{entry.user.name}</span>
									<span>•</span>
								{/if}
								<span class="shrink-0">{renderDate(entry.created_at)}</span>
							</div>
						</button>
					</div>
				{/each}

				{#if historyLoading}
					<div class="flex justify-center py-2">
						<Spinner className="size-3" />
					</div>
				{/if}
			</div>
		{:else if !historyLoading}
			<div class="text-xs text-gray-400 text-center py-6 italic">
				{$i18n.t('No history available')}
			</div>
		{/if}
	</div>
{/snippet}
