<script lang="ts">
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { toast } from 'svelte-sonner';
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { onMount, getContext, tick, onDestroy } from 'svelte';
	const i18n = getContext('i18n');

	import { WEBUI_NAME, user, skills as _skills } from '$lib/stores';
	import { goto } from '$app/navigation';
	import {
		getSkills,
		getSkillById,
		getSkillItems,
		exportSkills,
		createNewSkill,
		deleteSkillById,
		toggleSkillById
	} from '$lib/apis/skills';
	import { capitalizeFirstLetter, parseFrontmatter, formatSkillName } from '$lib/utils';
	import TagInput from '$lib/components/common/Tags/TagInput.svelte';

	import Tooltip from '../common/Tooltip.svelte';
	import ConfirmDialog from '../common/ConfirmDialog.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import EllipsisHorizontal from '../icons/EllipsisHorizontal.svelte';
	import GarbageBin from '../icons/GarbageBin.svelte';
	import Search from '../icons/Search.svelte';
	import Plus from '../icons/Plus.svelte';
	import XMark from '../icons/XMark.svelte';
	import Spinner from '../common/Spinner.svelte';
	import ViewSelector from './common/ViewSelector.svelte';
	import Badge from '$lib/components/common/Badge.svelte';
	import Switch from '../common/Switch.svelte';
	import SkillMenu from './Skills/SkillMenu.svelte';
	import Pagination from '../common/Pagination.svelte';

	let shiftKey = false;
	let loaded = false;

	let importFiles;
	let importInputElement: HTMLInputElement;

	let query = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;

	let selectedSkill = null;
	let showDeleteConfirm = false;

	let filteredItems = null;
	let total = null;
	let loading = false;

	let tagsContainerElement: HTMLDivElement;
	let viewOption = '';
	let page = 1;

	const loadSkillItems = async () => {
		if (!loaded) return;

		loading = true;
		try {
			const res = await getSkillItems(localStorage.token, query, viewOption, page).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);

			if (res) {
				filteredItems = res.items;
				total = res.total;
			}
		} catch (err) {
			console.error(err);
		} finally {
			loading = false;
		}
	};

	// Debounce only query changes
	$: if (query !== undefined) {
		loading = true;
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			page = 1;
			loadSkillItems();
		}, 300);
	}

	// Immediate response to page/filter changes
	$: if (page && viewOption !== undefined) {
		loadSkillItems();
	}

	const cloneHandler = async (skill) => {
		const _skill = await getSkillById(localStorage.token, skill.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (_skill) {
			sessionStorage.skill = JSON.stringify({
				..._skill,
				id: `${_skill.id}_clone`,
				name: `${_skill.name} (Clone)`
			});
			goto('/workspace/skills/create');
		}
	};

	const exportHandler = async (skill) => {
		const _skill = await getSkillById(localStorage.token, skill.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (_skill) {
			let blob = new Blob([JSON.stringify([_skill])], {
				type: 'application/json'
			});
			saveAs(blob, `skill-${_skill.id}-export-${Date.now()}.json`);
		}
	};

	const deleteHandler = async (skill) => {
		const res = await deleteSkillById(localStorage.token, skill.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Skill deleted successfully'));
		}

		page = 1;
		loadSkillItems();
		await _skills.set(await getSkills(localStorage.token));
	};

	onMount(async () => {
		viewOption = localStorage?.workspaceViewOption || '';
		loaded = true;

		const onKeyDown = (event) => {
			if (event.key === 'Shift') {
				shiftKey = true;
			}
		};

		const onKeyUp = (event) => {
			if (event.key === 'Shift') {
				shiftKey = false;
			}
		};

		const onBlur = () => {
			shiftKey = false;
		};

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);
		window.addEventListener('blur-sm', onBlur);

		return () => {
			clearTimeout(searchDebounceTimer);
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);
			window.removeEventListener('blur-sm', onBlur);
		};
	});

	onDestroy(() => {
		clearTimeout(searchDebounceTimer);
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Skills')} • {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<div class="flex flex-col h-full min-h-0 overflow-hidden">
	<div class="flex flex-col gap-2 px-1 mt-1.5 mb-4 shrink-0">
		<div class="flex justify-between items-center">
			<div class="flex items-center gap-3 shrink-0">
				<div class="flex items-center justify-center w-9 h-9 rounded-xl bg-amber-500/10 dark:bg-amber-500/15">
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5 text-amber-600 dark:text-amber-400">
						<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
					</svg>
				</div>
				<div>
					<div class="text-xl font-semibold">{$i18n.t('Skills')}</div>
					{#if total !== null}
						<div class="text-xs text-gray-500 dark:text-gray-400">{total} 项</div>
					{/if}
				</div>
			</div>

			<div class="flex w-full justify-end gap-1.5">
				<input
					bind:this={importInputElement}
					bind:files={importFiles}
					type="file"
					accept=".md,.json"
					hidden
					on:change={() => {
						if (importFiles && importFiles.length > 0) {
							const file = importFiles[0];
							const ext = file.name.split('.').pop()?.toLowerCase();

							if (ext === 'json') {
								const reader = new FileReader();
								reader.onload = async (event) => {
									try {
										const content = event.target?.result;
										if (typeof content !== 'string') return;

										const parsedSkills = JSON.parse(content);
										const items = Array.isArray(parsedSkills) ? parsedSkills : [parsedSkills];

										for (const skill of items) {
											await createNewSkill(localStorage.token, skill).catch((error) => {
												toast.error(`${error}`);
											});
										}

										toast.success($i18n.t('Skill imported successfully'));
										page = 1;
										loadSkillItems();
										_skills.set(await getSkills(localStorage.token));
									} catch (e) {
										toast.error($i18n.t('Invalid JSON file'));
									}
								};
								reader.readAsText(file);
							} else {
								const reader = new FileReader();
								reader.onload = (event) => {
									const mdContent = event.target?.result;
									if (typeof mdContent === 'string') {
										const fm = parseFrontmatter(mdContent);
										const fileName = file.name.replace(/\.md$/, '');
										const rawName = fm.name || fileName;
										const displayName = formatSkillName(rawName);
										sessionStorage.skill = JSON.stringify({
											name: displayName,
											id: fm.name || '',
											description: fm.description || '',
											content: mdContent,
											is_active: true,
											access_grants: []
										});
										goto('/workspace/skills/create');
									}
								};
								reader.readAsText(file);
							}

							importInputElement.value = '';
						}
					}}
				/>

			<!-- {#if $user?.role === 'admin' || $user?.permissions?.workspace?.skills}
				<button
					class="flex text-xs items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-gray-200 transition border border-gray-200/50 dark:border-gray-700/50"
					on:click={() => {
						importInputElement.click();
					}}
				>
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-3.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
					</svg>
					<span class="font-medium">{$i18n.t('Import')}</span>
				</button>
			{/if} -->

			<!-- {#if total && ($user?.role === 'admin' || $user?.permissions?.workspace?.skills)}
				<button
					class="flex text-xs items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-gray-200 transition border border-gray-200/50 dark:border-gray-700/50"
					on:click={async () => {
						const _skills = await exportSkills(localStorage.token).catch((error) => {
							toast.error(`${error}`);
							return null;
						});
						if (_skills) {
							let blob = new Blob([JSON.stringify(_skills)], {
								type: 'application/json'
							});
							saveAs(blob, `skills-export-${Date.now()}.json`);
						}
					}}
				>
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-3.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
					</svg>
					<span class="font-medium">{$i18n.t('Export')}</span>
				</button>
			{/if} -->

				{#if $user?.role === 'admin' || $user?.permissions?.workspace?.skills}
					<a
						class="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
						href="/workspace/skills/create"
					>
						<Plus className="size-3.5" strokeWidth="2.5" />
						<div class="hidden md:block text-xs">{$i18n.t('New Skill')}</div>
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
			<div class="flex flex-1 items-center bg-gray-50 dark:bg-gray-850 rounded-xl px-3 py-1.5 transition focus-within:ring-2 focus-within:ring-gray-300/50 dark:focus-within:ring-gray-600/50 focus-within:bg-white dark:focus-within:bg-gray-900">
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
				bind:this={tagsContainerElement}
			>
				<ViewSelector
					bind:value={viewOption}
					onChange={async (value) => {
						localStorage.workspaceViewOption = value;
						page = 1;
						await tick();
					}}
				/>
			</div>
		</div>

		{#if filteredItems === null || loading}
			<div class="w-full flex justify-center items-center py-16 flex-1">
				<Spinner className="size-5" />
			</div>
		{:else if (filteredItems ?? []).length !== 0}
			<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden mt-2 px-3">
			<div class="gap-2.5 grid lg:grid-cols-2">
				{#each filteredItems as skill}
					<div
						class="group flex text-left w-full px-4 py-3.5 transition-all duration-200 rounded-xl border border-transparent hover:border-gray-200/60 dark:hover:border-gray-700/40 hover:shadow-sm {skill.write_access
							? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-850/60'
							: 'opacity-70'}"
					>
						<div class="flex items-start gap-3 flex-1 min-w-0">
							<div class="flex items-center justify-center w-10 h-10 rounded-lg bg-amber-50 dark:bg-amber-500/10 shrink-0 mt-0.5 group-hover:bg-amber-100 dark:group-hover:bg-amber-500/20 transition-colors">
								<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5 text-amber-600 dark:text-amber-400">
									<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
								</svg>
							</div>
							{#if skill.write_access}
								<a
									class="flex-1 min-w-0"
									href={`/workspace/skills/edit?id=${encodeURIComponent(skill.id)}`}
								>
									<div class="flex items-center gap-2 mb-1">
										<Tooltip content={skill?.description ?? skill.name} placement="top-start">
											<div class="text-sm font-semibold line-clamp-1">
												{skill.name}
											</div>
										</Tooltip>
										<!-- Inactive badge hidden along with the disabled toggle
										{#if !skill.is_active}
											<Badge type="muted" content={$i18n.t('Inactive')} />
										{/if}
										-->
									</div>
									<div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
										<Tooltip
											content={skill?.user?.email ?? $i18n.t('Deleted User')}
											className="flex shrink-0"
											placement="top-start"
										>
											<span>{$i18n.t('By {{name}}', {
												name: capitalizeFirstLetter(
													skill?.user?.name ?? skill?.user?.email ?? $i18n.t('Deleted User')
												)
											})}</span>
										</Tooltip>
										{#if skill?.updated_at}
											<span class="text-gray-300 dark:text-gray-600">·</span>
											<Tooltip content={dayjs(skill.updated_at * 1000).format('LLLL')}>
												<span class="shrink-0">
													{$i18n.t('Updated')} {dayjs(skill.updated_at * 1000).fromNow()}
												</span>
											</Tooltip>
										{/if}
									</div>
								</a>
							{:else}
								<div class="flex-1 min-w-0">
									<div class="flex items-center justify-between gap-2 mb-1">
										<Tooltip content={skill?.description ?? skill.name} placement="top-start">
											<div class="flex items-center gap-2">
												<div class="text-sm font-semibold line-clamp-1">
													{skill.name}
												</div>
												<!-- Inactive badge hidden along with the disabled toggle
												{#if !skill.is_active}
													<Badge type="muted" content={$i18n.t('Inactive')} />
												{/if}
												-->
											</div>
										</Tooltip>
										<Badge type="muted" content={$i18n.t('Read Only')} />
									</div>
									<div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
										<Tooltip
											content={skill?.user?.email ?? $i18n.t('Deleted User')}
											className="flex shrink-0"
											placement="top-start"
										>
											<span>{$i18n.t('By {{name}}', {
												name: capitalizeFirstLetter(
													skill?.user?.name ?? skill?.user?.email ?? $i18n.t('Deleted User')
												)
											})}</span>
										</Tooltip>
										{#if skill?.updated_at}
											<span class="text-gray-300 dark:text-gray-600">·</span>
											<Tooltip content={dayjs(skill.updated_at * 1000).format('LLLL')}>
												<span class="shrink-0">
													{$i18n.t('Updated')} {dayjs(skill.updated_at * 1000).fromNow()}
												</span>
											</Tooltip>
										{/if}
									</div>
								</div>
							{/if}
						</div>
						{#if skill.write_access}
							<div class="flex flex-row gap-0.5 self-center opacity-0 group-hover:opacity-100 transition-opacity">
								{#if shiftKey}
									<Tooltip content={$i18n.t('Delete')}>
										<button
											class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
											type="button"
											aria-label={$i18n.t('Delete')}
											on:click={() => {
												deleteHandler(skill);
											}}
										>
											<GarbageBin />
										</button>
									</Tooltip>
								{:else}
									<SkillMenu
										editHandler={() => {
											goto(`/workspace/skills/edit?id=${encodeURIComponent(skill.id)}`);
										}}
										cloneHandler={() => {
											cloneHandler(skill);
										}}
										exportHandler={() => {
											exportHandler(skill);
										}}
										deleteHandler={async () => {
											selectedSkill = skill;
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
									</SkillMenu>
								{/if}

								<!-- Enable/Disable toggle temporarily disabled - admin disable affects all users globally
								<button on:click|stopPropagation|preventDefault>
									<Tooltip content={skill.is_active ? $i18n.t('Enabled') : $i18n.t('Disabled')}>
										<Switch
											bind:state={skill.is_active}
											on:change={async () => {
												toggleSkillById(localStorage.token, skill.id);
											}}
										/>
									</Tooltip>
								</button>
								-->

							</div>
						{/if}
					</div>
				{/each}
			</div>

			{#if total > 30}
				<div class="flex justify-center mt-4 mb-2">
					<Pagination bind:page count={total} perPage={30} />
				</div>
			{/if}
			</div>
		{:else}
			<div class="w-full flex flex-col justify-center items-center py-20 flex-1">
				<div class="max-w-sm text-center">
					<div class="flex items-center justify-center w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-800 mx-auto mb-4">
						<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-8 text-gray-400">
							<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
						</svg>
					</div>
					<div class="text-base font-semibold mb-1.5">{$i18n.t('No skills found')}</div>
				</div>
			</div>
		{/if}
	</div>

	</div>

	<DeleteConfirmDialog
		bind:show={showDeleteConfirm}
		title={$i18n.t('Delete skill?')}
		on:confirm={() => {
			deleteHandler(selectedSkill);
		}}
	>
		<div class=" text-sm text-gray-500 truncate">
			{$i18n.t('This will delete')} <span class="  font-medium">{selectedSkill.name}</span>.
		</div>
	</DeleteConfirmDialog>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner className="size-5" />
	</div>
{/if}
