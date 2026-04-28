<script>
	import { toast } from 'svelte-sonner';
	import { onMount, getContext } from 'svelte';
	import { page } from '$app/stores';

	const i18n = getContext('i18n');

	import { deleteGroupById, updateGroupById } from '$lib/apis/groups';

	import Pencil from '$lib/components/icons/Pencil.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import EditGroupModal from './EditGroupModal.svelte';

	export let group = {
		name: 'Admins',
		user_ids: [1, 2, 3]
	};

	export let groups = [];
	export let setGroups = () => {};

	let showEdit = false;
	let showDeleteConfirm = false;
	let wasEditOpen = false;

	$: {
		if (showEdit) {
			wasEditOpen = true;
		} else if (wasEditOpen) {
			wasEditOpen = false;
			setGroups();
		}
	}

	const updateHandler = async (_group) => {
		const res = await updateGroupById(localStorage.token, group.id, _group).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Group updated successfully'));
		}
	};

	const deleteHandler = async () => {
		const res = await deleteGroupById(localStorage.token, group.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Group deleted successfully'));
			setGroups();
		}
	};

	onMount(() => {
		const groupId = $page.url.searchParams.get('id');
		if (groupId && groupId === group.id) {
			showEdit = true;
		}
	});
</script>

<EditGroupModal
	bind:show={showEdit}
	edit
	{group}
	{groups}
	onSubmit={updateHandler}
	onDelete={deleteHandler}
/>

<ConfirmDialog
	bind:show={showDeleteConfirm}
	on:confirm={() => {
		deleteHandler();
	}}
/>

<tr class="border-t border-gray-50 dark:border-gray-850/50 text-xs hover:bg-gray-50/50 dark:hover:bg-gray-850/30 transition-colors cursor-pointer"
	on:click={() => { showEdit = true; }}
>
	<td class="px-4 py-2.5 font-medium text-gray-900 dark:text-white">
		<div class="flex items-center gap-2.5">
			<div class="flex items-center justify-center w-7 min-w-7 h-7 rounded-full bg-violet-100 dark:bg-violet-900/30 text-violet-600 dark:text-violet-400 flex-shrink-0">
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="size-3.5">
					<path d="M8 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3.156 11.763c.16-.629.44-1.21.813-1.72a2.5 2.5 0 0 0-2.725 1.377c-.136.287.102.58.418.58h1.449c.01-.077.025-.156.045-.237ZM12.847 11.763c.02.08.036.16.046.237h1.446c.316 0 .554-.293.417-.579a2.5 2.5 0 0 0-2.722-1.378c.374.51.653 1.09.813 1.72ZM14 7.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0ZM3.5 9a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM5 13c-.552 0-1.013-.455-.876-.99a4.002 4.002 0 0 1 7.753 0c.136.535-.324.99-.877.99H5Z" />
				</svg>
			</div>
			<div class="font-medium truncate">{group.name}</div>
		</div>
	</td>
	<td class="px-4 py-2.5 text-gray-500 dark:text-gray-400">
		<Tooltip content={group?.description || '-'}>
			<div class="truncate">
				{group?.description ?? '-'}
			</div>
		</Tooltip>
	</td>
	<td class="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-center">
		{group?.member_count ?? 0}
	</td>
	<td class="px-4 py-2.5 text-right">
		<div class="flex justify-end items-center gap-0.5">
			<Tooltip content={$i18n.t('Edit')}>
				<button
					class="p-1.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
					aria-label={$i18n.t('Edit')}
					on:click|stopPropagation={() => {
						showEdit = true;
					}}
				>
					<Pencil className="size-3.5" />
				</button>
			</Tooltip>

			<Tooltip content={$i18n.t('Delete')}>
				<button
					class="p-1.5 text-gray-400 hover:text-red-500 dark:text-gray-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
					aria-label={$i18n.t('Delete')}
					on:click|stopPropagation={() => {
						showDeleteConfirm = true;
					}}
				>
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
						<path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
					</svg>
				</button>
			</Tooltip>
		</div>
	</td>
</tr>
