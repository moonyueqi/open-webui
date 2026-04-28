<script lang="ts">
	import { getContext, onDestroy } from 'svelte';
	const i18n = getContext('i18n');

	import { getUsers } from '$lib/apis/users';
	import { toast } from 'svelte-sonner';

	import { addUserToGroup, removeUserFromGroup } from '$lib/apis/groups';
	import { WEBUI_API_BASE_URL } from '$lib/constants';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import Badge from '$lib/components/common/Badge.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	export let groupId: string;
	export let userCount = 0;

	let users = null;
	let total = null;

	let query = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;
	let orderBy = 'created_at'; // default sort key
	let direction = 'desc'; // default sort order

	let page = 1;

	const setSortKey = (key) => {
		if (orderBy === key) {
			direction = direction === 'asc' ? 'desc' : 'asc';
		} else {
			orderBy = key;
			direction = 'asc';
		}
		page = 1;
	};

	const getUserList = async () => {
		try {
			const res = await getUsers(localStorage.token, query, orderBy, direction, page).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);

			if (res) {
				users = res.users;
				total = res.total;
			}
		} catch (err) {
			console.error(err);
		}
	};

	const toggleMember = async (userId, state) => {
		if (state === 'checked') {
			const res = await addUserToGroup(localStorage.token, groupId, [userId]).catch((error) => {
				toast.error(`${error}`);
				return null;
			});
			if (res) userCount++;
		} else {
			const res = await removeUserFromGroup(localStorage.token, groupId, [userId]).catch((error) => {
				toast.error(`${error}`);
				return null;
			});
			if (res) userCount--;
		}

		getUserList();
	};

	$: if (page !== null && orderBy !== null && direction !== null) {
		getUserList();
	}

	$: if (query !== undefined) {
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			page = 1;
			getUserList();
		}, 300);
	}

	onDestroy(() => {
		clearTimeout(searchDebounceTimer);
	});
</script>

<div class=" max-h-full h-full w-full flex flex-col overflow-y-hidden">
	<div class="w-full h-fit mb-2">
		<div class="flex items-center gap-2 px-2 py-1.5 bg-gray-50 dark:bg-gray-850/60 rounded-xl border border-gray-200/60 dark:border-gray-700/40">
			<Search className="size-4 text-gray-400 shrink-0" />
			<input
				class="w-full text-sm outline-hidden bg-transparent placeholder:text-gray-400 dark:placeholder:text-gray-500"
				bind:value={query}
				placeholder={$i18n.t('Search users...')}
			/>
		</div>
	</div>

	{#if users === null || total === null}
		<div class="my-10 flex justify-center">
			<Spinner className="size-5" />
		</div>
	{:else}
		{@const memberUsers = users.filter((u) => (u?.group_ids ?? []).includes(groupId))}
		{@const nonMemberUsers = users.filter((u) => !(u?.group_ids ?? []).includes(groupId))}

		{#if users.length > 0}
			<div class="scrollbar-hidden relative overflow-y-auto max-w-full flex-1 space-y-3">
				{#if memberUsers.length > 0}
					<div>
						<div class="flex items-center gap-2 px-2 mb-1.5">
							<div class="text-xs font-medium text-gray-500 dark:text-gray-400">{$i18n.t('Current Members')}</div>
							<div class="text-xs text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded-md">{memberUsers.length}</div>
						</div>
						<div class="space-y-0.5">
							{#each memberUsers as user (user?.id)}
								<div class="flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-850/50 transition group">
									<div class="shrink-0">
										<Checkbox
											state="checked"
											on:change={(e) => {
												toggleMember(user.id, e.detail);
											}}
										/>
									</div>
									<img
										class="rounded-full w-7 h-7 object-cover shrink-0"
										src={`${WEBUI_API_BASE_URL}/users/${user.id}/profile/image`}
										alt="user"
									/>
									<div class="flex-1 min-w-0">
										<Tooltip content={user.email} placement="top-start">
											<div class="text-sm font-medium text-gray-900 dark:text-white truncate">{user.name}</div>
										</Tooltip>
										<div class="text-xs text-gray-400 dark:text-gray-500 truncate">{user.email}</div>
									</div>
								<Badge
									type={user.role === 'admin' ? 'info' : user.role === 'user' ? 'success' : 'muted'}
									content={$i18n.t(user.role)}
								/>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			{#if nonMemberUsers.length > 0}
					<div>
						<div class="flex items-center gap-2 px-2 mb-1.5 {memberUsers.length > 0 ? 'pt-2 border-t border-gray-100 dark:border-gray-800/50' : ''}">
							<div class="text-xs font-medium text-gray-500 dark:text-gray-400">{$i18n.t('Available Users')}</div>
							<div class="text-xs text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded-md">{nonMemberUsers.length}</div>
						</div>
						<div class="space-y-0.5">
							{#each nonMemberUsers as user (user?.id)}
								<div class="flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-850/50 transition group">
									<div class="shrink-0">
										<Checkbox
											state="unchecked"
											on:change={(e) => {
												toggleMember(user.id, e.detail);
											}}
										/>
									</div>
									<img
										class="rounded-full w-7 h-7 object-cover shrink-0 opacity-60 group-hover:opacity-100 transition"
										src={`${WEBUI_API_BASE_URL}/users/${user.id}/profile/image`}
										alt="user"
									/>
									<div class="flex-1 min-w-0">
										<Tooltip content={user.email} placement="top-start">
											<div class="text-sm font-medium text-gray-600 dark:text-gray-300 truncate">{user.name}</div>
										</Tooltip>
										<div class="text-xs text-gray-400 dark:text-gray-500 truncate">{user.email}</div>
									</div>
								<Badge
									type={user.role === 'admin' ? 'info' : user.role === 'user' ? 'success' : 'muted'}
									content={$i18n.t(user.role)}
								/>
							</div>
						{/each}
					</div>
				</div>
			{/if}
			</div>
		{:else}
			<div class="text-gray-500 text-xs text-center py-8 px-10">
				{$i18n.t('No users were found.')}
			</div>
		{/if}

		{#if total > 30}
			<Pagination bind:page count={total} perPage={30} />
		{/if}
	{/if}
</div>
