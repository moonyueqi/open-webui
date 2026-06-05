<script lang="ts">
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { toast } from 'svelte-sonner';
	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { user, skills as _skillsStore } from '$lib/stores';
	import {
		getSkillCategoryById,
		updateSkillCategoryById,
		getSkillsByCategoryId,
		deleteSkillCategoryById,
		updateSkillCategoryAccessGrants
	} from '$lib/apis/skill-categories';
	import { deleteSkillById, getSkills } from '$lib/apis/skills';
	import { capitalizeFirstLetter } from '$lib/utils';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import AccessControlModal from '../common/AccessControlModal.svelte';
	import ViewSelector from '../common/ViewSelector.svelte';
	import Plus from '../../icons/Plus.svelte';
	import GarbageBin from '../../icons/GarbageBin.svelte';
	import Search from '../../icons/Search.svelte';
	import XMark from '../../icons/XMark.svelte';

	const i18n = getContext('i18n');

	let id: string;
	let category: any = null;
	let skillItems: any[] | null = null;
	let skillsTotal: number | null = null;
	let skillsPage = 1;
	let loading = false;

	let showDeleteConfirm = false;
	let deleteSkillItem: any = null;
	let showAccessControlModal = false;

	let query = '';
	let viewOption = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;

	let editName = '';
	let editDescription = '';
	let debounceTimeout: ReturnType<typeof setTimeout> | null = null;

	const loadCategory = async () => {
		const res = await getSkillCategoryById(localStorage.token, id).catch((e) => {
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
			goto('/workspace/skills');
		}
	};

	const loadSkills = async () => {
		loading = true;
		const res = await getSkillsByCategoryId(
			localStorage.token,
			id,
			skillsPage,
			query,
			viewOption
		).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			skillItems = res.items;
			skillsTotal = res.total;
		}
		loading = false;
	};

	$: if (id && query !== undefined) {
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			skillsPage = 1;
			loadSkills();
		}, 300);
	}

	$: if (id && viewOption !== undefined) {
		skillsPage = 1;
		loadSkills();
	}

	$: if (skillsPage && id) {
		loadSkills();
	}

	const deleteSkillHandler = async (skill: any) => {
		const res = await deleteSkillById(localStorage.token, skill.id).catch((err) => {
			toast.error(`${err}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Skill deleted successfully'));
			await _skillsStore.set(await getSkills(localStorage.token));
		}

		skillsPage = 1;
		loadSkills();
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

			const res = await updateSkillCategoryById(
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
		title={$i18n.t('Delete skill?')}
		on:confirm={() => {
			deleteSkillHandler(deleteSkillItem);
		}}
	>
		<div class="text-sm text-gray-500 truncate">
			{$i18n.t('This will delete')} <span class="font-medium">{deleteSkillItem?.name}</span>.
		</div>
	</DeleteConfirmDialog>

	<AccessControlModal
		bind:show={showAccessControlModal}
		bind:accessGrants={category.access_grants}
		accessRoles={['read', 'write']}
		share={$user?.permissions?.sharing?.skills || $user?.role === 'admin'}
		sharePublic={$user?.permissions?.sharing?.public_skills || $user?.role === 'admin'}
		shareUsers={($user?.permissions?.access_grants?.allow_users ?? true) || $user?.role === 'admin'}
		onChange={async () => {
			try {
				await updateSkillCategoryAccessGrants(
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

	<div class="flex flex-col w-full h-full min-h-0">
		<div class="flex flex-col gap-2 px-1 mt-1.5 mb-4 shrink-0">
			<div class="flex justify-between items-center">
				<div class="flex items-center gap-3 min-w-0 flex-1">
					<button
						class="flex items-center justify-center w-9 h-9 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 transition-colors shrink-0"
						aria-label={$i18n.t('Back')}
						on:click={() => goto('/workspace/skills')}
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
						<a
							class="px-3 py-1.5 rounded-xl bg-gray-100 hover:bg-gray-200 text-black dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
							href={`/workspace/skills/create?category_id=${id}`}
						>
							<Plus className="size-3.5" strokeWidth="2.5" />
							<div class="hidden md:block text-xs">{$i18n.t('New Skill')}</div>
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
						aria-label={$i18n.t('Search Skills')}
						placeholder={$i18n.t('Search Skills')}
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

			{#if skillItems === null || loading}
				<div class="w-full flex justify-center items-center py-16 flex-1">
					<Spinner className="size-5" />
				</div>
			{:else if (skillItems ?? []).length !== 0}
				<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden px-3 mt-2">
					<div class="gap-2.5 grid lg:grid-cols-2">
						{#each skillItems as skill (skill.id)}
							<div
								class="group flex text-left w-full px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-850/60 transition-all duration-200 rounded-xl border border-transparent hover:border-gray-200/60 dark:hover:border-gray-700/40 hover:shadow-sm {category.write_access
									? ''
									: 'opacity-70'}"
							>
								<div class="flex items-start gap-3 flex-1 min-w-0">
									<div
										class="flex items-center justify-center w-10 h-10 rounded-lg bg-amber-50 dark:bg-amber-500/10 shrink-0 mt-0.5 group-hover:bg-amber-100 dark:group-hover:bg-amber-500/20 transition-colors"
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="1.5"
											stroke="currentColor"
											class="size-5 text-amber-600 dark:text-amber-400"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z"
											/>
										</svg>
									</div>
									<a
										class="flex-1 min-w-0"
										href={`/workspace/skills/edit?id=${encodeURIComponent(skill.id)}`}
									>
										<div class="flex items-center gap-2">
											<Tooltip content={skill?.description ?? skill.name} placement="top-start">
												<div class="text-sm font-semibold line-clamp-1">
													{skill.name}
												</div>
											</Tooltip>
										</div>
										{#if skill.description}
											<div class="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">
												{skill.description}
											</div>
										{/if}
										<div class="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500 mt-0.5">
											<Tooltip
												content={skill?.user?.email ?? $i18n.t('Deleted User')}
												className="flex shrink-0"
												placement="top-start"
											>
												<span class="shrink-0">
													{$i18n.t('By {{name}}', {
														name: capitalizeFirstLetter(
															skill?.user?.name ??
																skill?.user?.email ??
																$i18n.t('Deleted User')
														)
													})}
												</span>
											</Tooltip>
											{#if skill?.updated_at}
												<span class="text-gray-300 dark:text-gray-600">·</span>
												<Tooltip content={dayjs(skill.updated_at * 1000).format('LLLL')}>
													<span class="shrink-0">
														{$i18n.t('Updated')}
														{dayjs(skill.updated_at * 1000).fromNow()}
													</span>
												</Tooltip>
											{/if}
										</div>
									</a>
								</div>

								{#if category.write_access}
									<div
										class="flex flex-row gap-0.5 self-center opacity-0 group-hover:opacity-100 transition-opacity"
									>
										<Tooltip content={$i18n.t('Delete')}>
											<button
												class="self-center w-fit text-sm p-1.5 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
												type="button"
												aria-label={$i18n.t('Delete')}
												on:click|preventDefault|stopPropagation={() => {
													deleteSkillItem = skill;
													showDeleteConfirm = true;
												}}
											>
												<GarbageBin />
											</button>
										</Tooltip>
									</div>
								{/if}
							</div>
						{/each}
					</div>

					{#if skillsTotal && skillsTotal > 30}
						<div class="flex justify-center mt-4 mb-2">
							<Pagination bind:page={skillsPage} count={skillsTotal} perPage={30} />
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
									d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z"
								/>
							</svg>
						</div>
						<div class="text-base font-semibold mb-1.5">
							{$i18n.t('No skills in this category')}
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
