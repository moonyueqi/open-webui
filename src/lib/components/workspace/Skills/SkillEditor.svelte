<script lang="ts">
	import { onMount, tick, getContext } from 'svelte';

	import { toast } from 'svelte-sonner';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	import AccessControlModal from '../common/AccessControlModal.svelte';
	import { user } from '$lib/stores';
	import { slugify, parseFrontmatter, formatSkillName } from '$lib/utils';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { updateSkillAccessGrants } from '$lib/apis/skills';
	import { goto } from '$app/navigation';

	export let onSubmit: Function;
	export let edit = false;
	export let skill = null;
	export let clone = false;
	export let disabled = false;

	const i18n = getContext('i18n');

	let loading = false;

	let name = '';
	let id = '';
	let description = '';
	let content = '';

	let accessGrants = [];
	let showAccessControlModal = false;
	let hasManualEdit = false;
	let hasManualName = false;
	let hasManualDescription = false;
	let isFrontmatterDetected = false;

	// Only the resource owner or admin may modify access grants. A user with
	// `write` permission can edit content but cannot change who has access.
	$: canManageAccess =
		!edit ||
		$user?.role === 'admin' ||
		(skill?.user_id && skill.user_id === $user?.id);

	let contentLineCount = 1;
	$: contentLineCount = content ? content.split('\n').length : 1;

	$: if (!edit && content) {
		const fm = parseFrontmatter(content);
		if (fm.name) {
			isFrontmatterDetected = true;
			if (!hasManualName) {
				name = formatSkillName(fm.name);
			}
			if (!hasManualEdit) {
				id = fm.name;
			}
		} else {
			isFrontmatterDetected = false;
		}
		if (fm.description && !hasManualDescription) {
			description = fm.description;
		}
	} else if (!edit && !content) {
		isFrontmatterDetected = false;
	}

	$: if (!edit && !hasManualEdit && !isFrontmatterDetected) {
		id = name !== '' ? slugify(name) : '';
	}

	function handleIdInput(e: Event) {
		hasManualEdit = true;
	}

	function handleNameInput(e: Event) {
		hasManualName = true;
	}

	function handleDescriptionInput(e: Event) {
		hasManualDescription = true;
	}

	const submitHandler = async () => {
		if (disabled) {
			toast.error($i18n.t('You do not have permission to edit this skill.'));
			return;
		}
		loading = true;

		try {
			await onSubmit({
				id,
				name,
				description,
				content,
				is_active: true,
				meta: { tags: [] },
				access_grants: accessGrants
			});
		} finally {
			loading = false;
		}
	};

	onMount(async () => {
		if (skill) {
			name = skill.name || '';
			await tick();
			id = skill.id || '';
			description = skill.description || '';
			content = skill.content || '';
			accessGrants = skill?.access_grants === undefined ? [] : skill?.access_grants;

			if (name) hasManualName = true;
			if (description) hasManualDescription = true;
			if (id) hasManualEdit = true;
		}
	});
</script>

<AccessControlModal
	bind:show={showAccessControlModal}
	bind:accessGrants
	accessRoles={['read', 'write']}
	share={$user?.permissions?.sharing?.skills || $user?.role === 'admin'}
	sharePublic={$user?.permissions?.sharing?.public_skills || $user?.role === 'admin'}
	shareUsers={($user?.permissions?.access_grants?.allow_users ?? true) || $user?.role === 'admin'}
	onChange={async () => {
		if (edit && skill?.id) {
			try {
				await updateSkillAccessGrants(localStorage.token, skill.id, accessGrants);
				toast.success($i18n.t('Saved'));
			} catch (error) {
				toast.error(`${error}`);
			}
		}
	}}
/>

<div class="flex flex-col justify-between w-full overflow-y-auto h-full">
	<div class="mx-auto w-full md:px-0 h-full">
		<form class="flex flex-col max-h-[100dvh] h-full" on:submit|preventDefault={submitHandler}>
			<div class="flex flex-col flex-1 overflow-auto h-0">
				<!-- Header: Back + Title + Access -->
				<div class="w-full mb-4 flex flex-col gap-1.5 px-1">
					<div class="flex w-full items-center gap-2">
						<Tooltip content={$i18n.t('Back')}>
							<button
								class="shrink-0 p-1.5 rounded-xl text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-all duration-150"
								aria-label={$i18n.t('Back')}
								on:click={() => {
									goto('/workspace/skills');
								}}
								type="button"
							>
								<ChevronLeft strokeWidth="2.5" />
							</button>
						</Tooltip>

						<div class="flex-1 min-w-0">
							<Tooltip content={$i18n.t('e.g. Code Review Guidelines')} placement="top-start">
								<input
									class="w-full text-2xl font-semibold bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600 tracking-tight"
									type="text"
									placeholder={$i18n.t('Skill Name')}
									aria-label={$i18n.t('Skill Name')}
									bind:value={name}
									on:input={handleNameInput}
									required
									{disabled}
								/>
							</Tooltip>
						</div>

						<div class="shrink-0 flex items-center gap-2">
							{#if !disabled}
								{#if canManageAccess}
									<button
										class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600 transition-all duration-150"
										type="button"
										on:click={() => (showAccessControlModal = true)}
									>
										<LockClosed strokeWidth="2.5" className="size-3.5" />
										{$i18n.t('Access')}
									</button>
								{/if}
							{:else}
								<span
									class="inline-flex items-center gap-1 text-xs font-medium text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800/50 px-2.5 py-1 rounded-lg"
								>
									<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="size-3">
										<path d="M8 1a3.5 3.5 0 0 0-3.5 3.5V7A1.5 1.5 0 0 0 3 8.5v4A1.5 1.5 0 0 0 4.5 14h7a1.5 1.5 0 0 0 1.5-1.5v-4A1.5 1.5 0 0 0 11.5 7V4.5A3.5 3.5 0 0 0 8 1Zm2 6V4.5a2 2 0 1 0-4 0V7h4Z" />
									</svg>
									{$i18n.t('Read Only')}
								</span>
							{/if}
						</div>
					</div>

					<!-- ID + Description row, aligned with title via matching back-button placeholder -->
					<div class="flex items-center gap-2">
						<!-- Invisible spacer matching the back button width -->
						<div class="shrink-0 p-1.5 invisible">
							<ChevronLeft strokeWidth="2.5" />
						</div>

						<div class="flex-1 min-w-0 flex gap-3 items-center">
							{#if edit}
								<div class="shrink-0 text-xs font-mono text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
									{id}
								</div>
							{:else}
								<Tooltip
									className="shrink-0"
									content={$i18n.t('e.g. code-review-guidelines')}
									placement="top-start"
								>
									<input
										class="w-40 text-xs font-mono text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 outline-hidden rounded-md px-2 py-1 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-1 focus:ring-blue-400/20 transition-all duration-150"
										type="text"
										placeholder={$i18n.t('Skill ID')}
										aria-label={$i18n.t('Skill ID')}
										bind:value={id}
										on:input={handleIdInput}
										required
										disabled={edit}
									/>
								</Tooltip>
							{/if}

							<div class="h-4 w-px bg-gray-200 dark:bg-gray-700" />

							<Tooltip
								className="flex-1 min-w-0"
								content={$i18n.t('e.g. Step-by-step instructions for code reviews')}
								placement="top-start"
							>
								<input
									class="w-full text-sm text-gray-600 dark:text-gray-400 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
									type="text"
									placeholder={$i18n.t('Skill Description')}
									aria-label={$i18n.t('Skill Description')}
									bind:value={description}
									on:input={handleDescriptionInput}
									{disabled}
								/>
							</Tooltip>
						</div>
					</div>
				</div>

				<!-- Content editor area -->
				<div class="mb-2 flex-1 overflow-auto h-0 px-1">
					<div class="h-full flex flex-col">
						<div
							class="relative bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-750 flex-1 min-h-0 overflow-hidden flex flex-col shadow-sm"
						>
							<!-- Editor toolbar -->
							<div class="flex items-center justify-between px-4 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-850/50">
								<div class="flex items-center gap-2">
									<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4 text-gray-400 dark:text-gray-500">
										<path fill-rule="evenodd" d="M4.5 2A1.5 1.5 0 0 0 3 3.5v13A1.5 1.5 0 0 0 4.5 18h11a1.5 1.5 0 0 0 1.5-1.5V7.621a1.5 1.5 0 0 0-.44-1.06l-4.12-4.122A1.5 1.5 0 0 0 11.378 2H4.5Zm2.25 8.5a.75.75 0 0 0 0 1.5h6.5a.75.75 0 0 0 0-1.5h-6.5Zm0 3a.75.75 0 0 0 0 1.5h6.5a.75.75 0 0 0 0-1.5h-6.5Z" clip-rule="evenodd" />
									</svg>
									<span class="text-xs font-medium text-gray-500 dark:text-gray-400">
										{$i18n.t('Skill Instructions')}
									</span>
									<span class="text-[10px] text-gray-400 dark:text-gray-500 font-mono">
										Markdown
									</span>
								</div>
								<div class="text-[10px] text-gray-400 dark:text-gray-600 font-mono tabular-nums">
									{contentLineCount} {$i18n.t('lines')}
								</div>
							</div>

							{#if disabled}
								<div class="px-5 py-4 overflow-y-auto flex-1">
									<pre class="text-sm whitespace-pre-wrap font-mono leading-relaxed text-gray-700 dark:text-gray-300">{content}</pre>
								</div>
							{:else}
								<textarea
									class="w-full flex-1 text-sm bg-transparent outline-hidden resize-none font-mono px-5 py-4 leading-relaxed placeholder:text-gray-300 dark:placeholder:text-gray-600"
									bind:value={content}
									placeholder={$i18n.t('Enter skill instructions in markdown...')}
									aria-label={$i18n.t('Skill Instructions')}
									required
								/>
							{/if}
						</div>
					</div>
				</div>

				<!-- Bottom action bar -->
				<div class="px-1 pb-3 flex items-center justify-between">
					<div class="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
						{#if edit && skill?.id}
							<span class="font-mono">{skill.id}</span>
						{/if}
					</div>

					{#if !disabled}
						<button
							class="inline-flex items-center gap-2 px-5 py-2 text-sm font-medium bg-black hover:bg-gray-800 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition-all duration-150 rounded-xl shadow-sm hover:shadow active:scale-[0.98]"
							type="submit"
							disabled={loading}
						>
							{#if loading}
								<Spinner className="size-4" />
							{/if}
							{$i18n.t(edit ? 'Save' : 'Save & Create')}
						</button>
					{/if}
				</div>
			</div>
		</form>
	</div>
</div>
