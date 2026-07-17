<script lang="ts">
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { toast } from 'svelte-sonner';
	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { user } from '$lib/stores';
	import {
		getPromptCategoryById,
		updatePromptCategoryById,
		getPromptsByCategoryId,
		deletePromptCategoryById,
		updatePromptCategoryAccessGrants
	} from '$lib/apis/prompt-categories';
	import { createNewPrompt, deletePromptById, togglePromptById, updatePromptById, getPromptById } from '$lib/apis/prompts';
	import { capitalizeFirstLetter, copyToClipboard, validateInputVariables } from '$lib/utils';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import AccessControlModal from '../common/AccessControlModal.svelte';
	import ViewSelector from '../common/ViewSelector.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import Plus from '../../icons/Plus.svelte';
	import XMark from '../../icons/XMark.svelte';
	import GarbageBin from '../../icons/GarbageBin.svelte';
	import Clipboard from '../../icons/Clipboard.svelte';
	import Check from '../../icons/Check.svelte';
	import InfoCircle from '../../icons/InfoCircle.svelte';

	const i18n = getContext('i18n');

	let id: string;
	let category: any = null;
	let prompts: any[] | null = null;
	let promptsTotal: number | null = null;
	let promptsPage = 1;
	let loading = false;

	let showDeleteConfirm = false;
	let deletePromptItem: any = null;
	let showAccessControlModal = false;

	let copiedId: string | null = null;

	let showCreatePromptModal = false;
	let createPromptName = '';
	let createPromptContent = '';
	let createPromptLoading = false;

	let showEditPromptModal = false;
	let editPromptItem: any = null;
	let editPromptName = '';
	let editPromptContent = '';
	let editPromptLoading = false;

	let editName = '';
	let editDescription = '';
	let debounceTimeout: ReturnType<typeof setTimeout> | null = null;

	let viewOption = '';

	const loadCategory = async () => {
		const res = await getPromptCategoryById(localStorage.token, id).catch((e) => {
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
			goto('/workspace/prompts');
		}
	};

	const loadPrompts = async () => {
		loading = true;
		const res = await getPromptsByCategoryId(
			localStorage.token,
			id,
			promptsPage,
			'',
			viewOption
		).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			prompts = res.items;
			promptsTotal = res.total;
		}
		loading = false;
	};

	$: if (id && viewOption !== undefined) {
		promptsPage = 1;
		loadPrompts();
	}

	$: if (promptsPage && id) {
		loadPrompts();
	}

	const deletePromptHandler = async (prompt: any) => {
		const res = await deletePromptById(localStorage.token, prompt.id).catch((err) => {
			toast.error(`${err}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Deleted {{name}}', { name: prompt.name }));
		}

		promptsPage = 1;
		loadPrompts();
	};

	const copyHandler = async (prompt: any) => {
		const res = await copyToClipboard(prompt.content);
		if (res) {
			copiedId = prompt.id;
			setTimeout(() => {
				copiedId = null;
			}, 2000);
		}
	};

	const showVariableIssues = (text: string): boolean => {
		const issues = validateInputVariables(text);
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
		return !hasError;
	};

	const createPromptHandler = async () => {
		if (!showVariableIssues(createPromptContent)) return;

		createPromptLoading = true;
		const trimmedName = createPromptName.trim();
		const res = await createNewPrompt(localStorage.token, {
			...(trimmedName ? { name: trimmedName } : {}),
			content: createPromptContent,
			category_id: id
		}).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Prompt created successfully'));
			showCreatePromptModal = false;
			createPromptName = '';
			createPromptContent = '';
			promptsPage = 1;
			await loadPrompts();
		}
		createPromptLoading = false;
	};


	const openEditPromptModal = async (prompt: any) => {
		editPromptItem = prompt;
		editPromptName = prompt.name || '';
		editPromptContent = prompt.content || '';
		showEditPromptModal = true;

		const fullPrompt = await getPromptById(localStorage.token, prompt.id).catch((e) => {
			toast.error(`${e}`);
			return null;
		});
		if (fullPrompt) {
			editPromptName = fullPrompt.name || '';
			editPromptContent = fullPrompt.content || '';
			editPromptItem = { ...prompt, ...fullPrompt };
		}
	};

	const editPromptHandler = async () => {
		if (!editPromptItem) return;
		if (!category?.write_access) {
			toast.error($i18n.t('You do not have permission to edit this prompt.'));
			return;
		}

		if (!showVariableIssues(editPromptContent)) return;

		editPromptLoading = true;

		const trimmedName = editPromptName.trim();
		const res = await updatePromptById(localStorage.token, {
			id: editPromptItem.id,
			...(trimmedName ? { name: trimmedName } : {}),
			content: editPromptContent
		}).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Prompt updated successfully'));
			showEditPromptModal = false;
			editPromptItem = null;
			editPromptName = '';
			editPromptContent = '';
			await loadPrompts();
		}
		editPromptLoading = false;
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

			const res = await updatePromptCategoryById(
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
	});
</script>

{#if category}
	<DeleteConfirmDialog
		bind:show={showDeleteConfirm}
		title={$i18n.t('Delete prompt?')}
		on:confirm={() => {
			deletePromptHandler(deletePromptItem);
		}}
	>
		<div class="text-sm text-gray-500 truncate">
			{$i18n.t('This will delete')} <span class="font-medium">{deletePromptItem?.name}</span>.
		</div>
	</DeleteConfirmDialog>

	<AccessControlModal
		bind:show={showAccessControlModal}
		bind:accessGrants={category.access_grants}
		accessRoles={['read', 'write']}
		share={$user?.permissions?.sharing?.prompts || $user?.role === 'admin'}
		sharePublic={$user?.permissions?.sharing?.public_prompts || $user?.role === 'admin'}
		shareUsers={($user?.permissions?.access_grants?.allow_users ?? true) ||
			$user?.role === 'admin'}
		onChange={async () => {
			try {
				await updatePromptCategoryAccessGrants(
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

	<Modal size="sm" bind:show={showCreatePromptModal}>
		<div class="px-5 pt-4 pb-5">
			<div class="flex justify-between items-center mb-4">
				<div class="flex items-center gap-2.5">
					<div class="p-2 rounded-xl bg-gray-100 dark:bg-gray-800">
						<svg
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
							stroke-width="1.5"
							stroke="currentColor"
							class="w-5 h-5 text-gray-600 dark:text-gray-300"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
							/>
						</svg>
					</div>
					<div class="text-lg font-semibold">{$i18n.t('Create a prompt')}</div>
				</div>
				<button
					class="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition"
					aria-label={$i18n.t('Close')}
					on:click={() => (showCreatePromptModal = false)}
				>
					<XMark className="size-5" />
				</button>
			</div>

			<form on:submit|preventDefault={createPromptHandler}>
				<div class="mb-3">
					<label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
						{$i18n.t('Prompt Title')}
					</label>
					<input
						type="text"
						class="w-full rounded-xl py-2.5 px-4 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-300 outline-hidden border border-gray-300 dark:border-gray-700 focus:border-black dark:focus:border-white focus:ring-0 transition placeholder:text-gray-400 dark:placeholder:text-gray-500"
						placeholder={$i18n.t('Give this prompt a title (optional)')}
						bind:value={createPromptName}
					/>
				</div>
				<div class="mb-3">
					<label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
						{$i18n.t('Prompt Content')} <span class="text-red-500">*</span>
					</label>
				<textarea
					class="w-full rounded-xl py-2.5 px-4 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-300 outline-hidden border border-gray-300 dark:border-gray-700 focus:border-black dark:focus:border-white focus:ring-0 transition placeholder:text-gray-400 dark:placeholder:text-gray-500 overflow-y-auto scrollbar-thin"
					placeholder={$i18n.t('Enter the prompt content that the AI will follow to generate a response...')}
					bind:value={createPromptContent}
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

				<div class="flex justify-end">
					<button
						class="px-3.5 py-1.5 text-xs font-medium transition rounded-lg flex items-center gap-1.5 {createPromptLoading
							? 'cursor-not-allowed bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500'
							: 'bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100'}"
						type="submit"
						disabled={createPromptLoading}
					>
						{#if createPromptLoading}
							<Spinner className="size-4" />
						{/if}
						{$i18n.t('Save & Create')}
					</button>
				</div>
			</form>
		</div>
	</Modal>

	<Modal size="sm" bind:show={showEditPromptModal}>
		<div class="px-5 pt-4 pb-5">
			<div class="flex justify-between items-center mb-4">
				<div class="flex items-center gap-2.5">
					<div class="p-2 rounded-xl bg-gray-100 dark:bg-gray-800">
						<svg
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
							stroke-width="1.5"
							stroke="currentColor"
							class="w-5 h-5 text-gray-600 dark:text-gray-300"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
							/>
						</svg>
					</div>
					<div class="text-lg font-semibold">
						{category?.write_access ? $i18n.t('Edit Prompt') : $i18n.t('View Prompt')}
					</div>
				</div>
				<button
					class="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition"
					aria-label={$i18n.t('Close')}
					on:click={() => (showEditPromptModal = false)}
				>
					<XMark className="size-5" />
				</button>
			</div>

			<form on:submit|preventDefault={editPromptHandler}>
				<div class="mb-3">
					<label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
						{$i18n.t('Prompt Title')}
					</label>
					<input
						type="text"
						class="w-full rounded-xl py-2.5 px-4 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-300 outline-hidden border border-gray-300 dark:border-gray-700 focus:border-black dark:focus:border-white focus:ring-0 transition placeholder:text-gray-400 dark:placeholder:text-gray-500 disabled:opacity-70 disabled:cursor-not-allowed"
						placeholder={$i18n.t('Give this prompt a title (optional)')}
						bind:value={editPromptName}
						disabled={!category?.write_access}
						readonly={!category?.write_access}
					/>
				</div>
				<div class="mb-3">
					<label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
						{$i18n.t('Prompt Content')}{#if category?.write_access} <span class="text-red-500">*</span>{/if}
					</label>
					<textarea
						class="w-full rounded-xl py-2.5 px-4 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-300 outline-hidden border border-gray-300 dark:border-gray-700 focus:border-black dark:focus:border-white focus:ring-0 transition placeholder:text-gray-400 dark:placeholder:text-gray-500 overflow-y-auto scrollbar-thin disabled:opacity-70 disabled:cursor-not-allowed"
						placeholder={$i18n.t('Enter the prompt content that the AI will follow to generate a response...')}
						bind:value={editPromptContent}
						rows="6"
						style="max-height: 300px;"
						required
						disabled={!category?.write_access}
						readonly={!category?.write_access}
					></textarea>

					{#if category?.write_access}
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
					{/if}
				</div>

				<div class="flex justify-end">
					{#if category?.write_access}
						<button
							class="px-3.5 py-1.5 text-xs font-medium transition rounded-lg flex items-center gap-1.5 {editPromptLoading
								? 'cursor-not-allowed bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500'
								: 'bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100'}"
							type="submit"
							disabled={editPromptLoading}
						>
							{#if editPromptLoading}
								<Spinner className="size-4" />
							{/if}
							{$i18n.t('Save')}
						</button>
					{:else}
						<button
							class="px-3.5 py-1.5 text-xs font-medium transition rounded-lg flex items-center gap-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200"
							type="button"
							on:click={() => (showEditPromptModal = false)}
						>
							{$i18n.t('Close')}
						</button>
					{/if}
				</div>
			</form>
		</div>
	</Modal>

	<div class="flex flex-col w-full h-full min-h-0">
		<div class="flex flex-col gap-2 px-1 mt-1.5 mb-4 shrink-0">
			<div class="flex justify-between items-center">
				<div class="flex items-center gap-3 min-w-0 flex-1">
					<button
						class="flex items-center justify-center w-9 h-9 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 transition-colors shrink-0"
						aria-label={$i18n.t('Back')}
						on:click={() => goto('/workspace/prompts')}
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
							class="text-xl font-semibold bg-transparent outline-hidden border-none p-0 focus:ring-0"
							bind:value={editName}
							aria-label={$i18n.t('Category Name')}
							placeholder={$i18n.t('Category Name')}
							disabled={!category.write_access}
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
							disabled={!category.write_access}
							on:input={() => {
								changeDebounceHandler();
							}}
						/>
					</div>
				</div>
				</div>

				<div class="flex items-center gap-2 shrink-0">
					{#if category.user_id === $user?.id || $user?.role === 'admin'}
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
					<button
						class="px-3 py-1.5 rounded-xl bg-gray-100 hover:bg-gray-200 text-black dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
						on:click={() => {
							createPromptName = '';
							createPromptContent = '';
							showCreatePromptModal = true;
						}}
					>
						<Plus className="size-3.5" strokeWidth="2.5" />
						<div class="hidden md:block text-xs">{$i18n.t('New Prompt')}</div>
					</button>
				{/if}
				</div>
			</div>
		</div>

		<div
			class="py-2.5 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm min-h-0 flex flex-col overflow-hidden flex-1"
		>
			<div
				class="px-3.5 pt-1.5 flex w-full bg-transparent overflow-x-auto scrollbar-none shrink-0"
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

			{#if prompts === null || loading}
				<div class="w-full flex justify-center items-center py-16 flex-1">
					<Spinner className="size-5" />
				</div>
			{:else if (prompts ?? []).length !== 0}
				<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden px-3 mt-2">
					<div class="gap-2.5 grid lg:grid-cols-2">
						{#each prompts as prompt (prompt.id)}
							<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
							<div
								class="group flex text-left w-full px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-850/60 transition-all duration-200 rounded-xl border border-transparent hover:border-gray-200/60 dark:hover:border-gray-700/40 hover:shadow-sm cursor-pointer"
								on:click={() => openEditPromptModal(prompt)}
							>
								<div class="flex items-start gap-3 flex-1 min-w-0">
									<div
										class="flex items-center justify-center w-10 h-10 rounded-lg bg-violet-50 dark:bg-violet-500/10 shrink-0 mt-0.5 group-hover:bg-violet-100 dark:group-hover:bg-violet-500/20 transition-colors"
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="1.5"
											stroke="currentColor"
											class="size-5 text-violet-600 dark:text-violet-400"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
											/>
										</svg>
									</div>
									<div class="flex-1 min-w-0">
										<div class="flex items-center justify-between w-full">
											<div class="font-semibold text-sm line-clamp-1 capitalize">
												{prompt.name}
											</div>
										</div>
										{#if prompt.content}
											<div class="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">
												{prompt.content}
											</div>
										{/if}
										<div
											class="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500 mt-0.5"
										>
										<Tooltip
											content={prompt?.user?.email ?? $i18n.t('Deleted User')}
											className="flex shrink-0"
											placement="top-start"
										>
											<span class="shrink-0">
												{$i18n.t('By {{name}}', {
													name: capitalizeFirstLetter(
														prompt?.user?.name ??
															prompt?.user?.email ??
															$i18n.t('Deleted User')
													)
												})}
											</span>
										</Tooltip>
										{#if prompt.updated_at}
											<span class="text-gray-300 dark:text-gray-600">·</span>
											<Tooltip content={dayjs(prompt.updated_at * 1000).format('LLLL')}>
												<span class="shrink-0">
													{$i18n.t('Updated')} {dayjs(prompt.updated_at * 1000).fromNow()}
												</span>
											</Tooltip>
										{/if}
										</div>
									</div>
								</div>
							<div
								class="flex flex-row gap-0.5 self-center opacity-0 group-hover:opacity-100 transition-opacity"
							>
								<Tooltip content={$i18n.t('Copy Prompt')}>
									<button
										class="self-center w-fit text-sm p-1.5 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
										type="button"
										aria-label={$i18n.t('Copy Prompt')}
										on:click|preventDefault|stopPropagation={() => {
											copyHandler(prompt);
										}}
									>
										{#if copiedId === prompt.id}
											<Check className="size-4" strokeWidth="1.5" />
										{:else}
											<Clipboard className="size-4" strokeWidth="1.5" />
										{/if}
									</button>
								</Tooltip>

								{#if category.write_access}
									<Tooltip content={$i18n.t('Delete')}>
										<button
											class="self-center w-fit text-sm p-1.5 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
											type="button"
											aria-label={$i18n.t('Delete')}
											on:click|preventDefault|stopPropagation={() => {
												deletePromptItem = prompt;
												showDeleteConfirm = true;
											}}
										>
											<GarbageBin />
										</button>
									</Tooltip>
								{/if}

								<!-- Enable/Disable toggle temporarily disabled - admin disable affects all users globally
								<button on:click|stopPropagation|preventDefault>
									<Tooltip
										content={prompt.is_active !== false
											? $i18n.t('Enabled')
											: $i18n.t('Disabled')}
									>
										<Switch
											bind:state={prompt.is_active}
											on:change={async () => {
												togglePromptById(localStorage.token, prompt.id);
											}}
										/>
									</Tooltip>
								</button>
								-->

							</div>
							</div>
						{/each}
					</div>

					{#if promptsTotal && promptsTotal > 30}
						<div class="flex justify-center mt-4 mb-2">
							<Pagination bind:page={promptsPage} count={promptsTotal} perPage={30} />
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
									d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
								/>
							</svg>
						</div>
					<div class="text-base font-semibold mb-1.5">
						{$i18n.t('No prompts in this category')}
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
