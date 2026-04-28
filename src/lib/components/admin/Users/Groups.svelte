<script>
	import { toast } from 'svelte-sonner';

	import { onMount, getContext } from 'svelte';
	import { goto } from '$app/navigation';

	import { user } from '$lib/stores';

	import Plus from '$lib/components/icons/Plus.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import EditGroupModal from './Groups/EditGroupModal.svelte';
	import GroupItem from './Groups/GroupItem.svelte';
	import { createNewGroup, getGroups } from '$lib/apis/groups';

	const i18n = getContext('i18n');

	let loaded = false;

	let groups = [];
	let query = '';

	let showAddGroupModal = false;

	$: filteredGroups = query
		? groups.filter(
				(g) =>
					g.name.toLowerCase().includes(query.toLowerCase()) ||
					(g.description && g.description.toLowerCase().includes(query.toLowerCase()))
			)
		: groups;

	const setGroups = async () => {
		groups = await getGroups(localStorage.token);
	};

	const addGroupHandler = async (group) => {
		const res = await createNewGroup(localStorage.token, group).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Group created successfully'));
			groups = await getGroups(localStorage.token);
		}
	};

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
			return;
		}

		await setGroups();
		loaded = true;
	});
</script>

<EditGroupModal
	bind:show={showAddGroupModal}
	edit={false}
	{groups}
	onSubmit={addGroupHandler}
/>

{#if !loaded}
	<div class="flex items-center justify-center py-16">
		<Spinner className="size-6" />
	</div>
{:else}
	<div
		class="pt-1 pb-3 gap-3 flex flex-col md:flex-row md:items-center justify-between sticky top-0 z-10 bg-white dark:bg-gray-900"
	>
		<div class="flex items-center gap-3">
			<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">
				{$i18n.t('Groups')}
			</div>

			<div class="flex items-center">
				<span class="inline-flex items-center text-sm font-medium px-2.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
					{groups.length}
				</span>
			</div>
		</div>

		<div class="flex items-center gap-2">
			<div class="flex items-center flex-1 md:w-64 rounded-xl px-3 py-1.5 bg-gray-50 dark:bg-gray-850 border border-gray-100 dark:border-gray-800 focus-within:border-gray-300 dark:focus-within:border-gray-600 transition-colors">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0"
				>
					<path
						fill-rule="evenodd"
						d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
						clip-rule="evenodd"
					/>
				</svg>
				<input
					class="w-full text-sm pl-2 outline-hidden bg-transparent text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
					bind:value={query}
					aria-label={$i18n.t('Search')}
					placeholder={$i18n.t('Search')}
				/>
			</div>

			<Tooltip content={$i18n.t('New Group')}>
				<button
					class="flex items-center justify-center p-2 rounded-xl bg-gray-50 dark:bg-gray-850 border border-gray-100 dark:border-gray-800 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-gray-600 dark:text-gray-300"
					on:click={() => {
						showAddGroupModal = !showAddGroupModal;
					}}
				>
					<Plus className="size-4" />
				</button>
			</Tooltip>
		</div>
	</div>

	{#if filteredGroups.length !== 0}
		<div class="scrollbar-hidden relative overflow-x-auto max-w-full rounded-xl border border-gray-100 dark:border-gray-800">
			<table class="w-full text-sm text-left text-gray-600 dark:text-gray-400 table-fixed max-w-full">
				<colgroup>
					<col class="w-[20%]" />
					<col class="w-auto" />
					<col class="w-[80px]" />
					<col class="w-[80px]" />
				</colgroup>
				<thead class="text-xs uppercase bg-gray-50/80 dark:bg-gray-850/50 text-gray-500 dark:text-gray-400">
					<tr>
						<th scope="col" class="px-4 py-3 font-semibold">{$i18n.t('Name')}</th>
						<th scope="col" class="px-4 py-3 font-semibold">{$i18n.t('Description')}</th>
						<th scope="col" class="px-4 py-3 font-semibold">{$i18n.t('Member Count')}</th>
						<th scope="col" class="px-4 py-3 text-right" />
					</tr>
				</thead>
				<tbody>
					{#each filteredGroups as group (group.id)}
						<GroupItem {group} {groups} {setGroups} />
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="scrollbar-hidden relative overflow-x-auto max-w-full rounded-xl border border-gray-100 dark:border-gray-800">
			<div class="w-full h-full flex flex-col justify-center items-center my-16 mb-24">
				<div class="max-w-md text-center">
					<div class="text-3xl mb-3">👥</div>
					<div class="text-lg font-medium mb-1 text-gray-900 dark:text-gray-100">{$i18n.t('No groups found')}</div>
					<div class="text-gray-500 dark:text-gray-400 text-center text-xs">
						{$i18n.t('Use groups to organize your users and assign permissions.')}
					</div>
				</div>
			</div>
		</div>
	{/if}
{/if}
