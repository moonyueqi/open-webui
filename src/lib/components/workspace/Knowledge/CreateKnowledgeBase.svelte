<script>
	import { toast } from 'svelte-sonner';

	import { goto } from '$app/navigation';
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');

	import { user } from '$lib/stores';
	import { createNewKnowledge } from '$lib/apis/knowledge';

	import AccessControl from '../common/AccessControl.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	let loading = false;

	let name = '';
	let description = '';
	let accessGrants = [];

	const submitHandler = async () => {
		loading = true;

		if (name.trim() === '') {
			toast.error($i18n.t('Please enter a knowledge base name.'));
			name = '';
			loading = false;
			return;
		}

		const res = await createNewKnowledge(localStorage.token, name, description, accessGrants).catch(
			(e) => {
				toast.error(`${e}`);
			}
		);

		if (res) {
			toast.success($i18n.t('Knowledge created successfully.'));
			goto(`/workspace/knowledge/${res.id}`);
		}

		loading = false;
	};
</script>

<div class="w-full h-full overflow-y-auto scrollbar-hidden">
	<button
		class="flex items-center gap-1.5 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 transition"
		on:click={() => {
			goto('/workspace/knowledge');
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
		on:submit|preventDefault={() => {
			submitHandler();
		}}
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
							d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25"
						/>
					</svg>
				</div>
				<div>
					<h1 class="text-xl font-semibold font-primary">
						{$i18n.t('Create a knowledge base')}
					</h1>
				</div>
			</div>

			<div class="w-full flex flex-col gap-4">
				<div class="w-full">
					<label for="kb-name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
						{$i18n.t('Name')} <span class="text-red-500">*</span>
					</label>
					<input
						id="kb-name"
						class="w-full rounded-xl py-2.5 px-4 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-300 outline-hidden border border-gray-800 dark:border-gray-300 focus:border-black dark:focus:border-white focus:ring-0 transition placeholder:text-gray-400 dark:placeholder:text-gray-500"
						type="text"
						bind:value={name}
						placeholder={$i18n.t('Please enter a knowledge base name')}
						required
					/>
				</div>

				<div class="w-full">
					<label for="kb-desc" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
						{$i18n.t('Description')}
						<span class="text-xs font-normal text-gray-400 dark:text-gray-500 ml-1">({$i18n.t('Optional')})</span>
					</label>
					<textarea
						id="kb-desc"
						class="w-full rounded-xl py-2.5 px-4 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-300 outline-hidden border border-gray-800 dark:border-gray-300 focus:border-black dark:focus:border-white focus:ring-0 transition placeholder:text-gray-400 dark:placeholder:text-gray-500 overflow-y-auto scrollbar-thin"
						rows="4"
						style="max-height: 200px;"
						bind:value={description}
						placeholder={$i18n.t('Add a description for this knowledge base (optional)')}
					></textarea>
				</div>
			</div>
		</div>

		<div class="mt-5">
			<AccessControl
				bind:accessGrants
				accessRoles={['read', 'write']}
				share={$user?.permissions?.sharing?.knowledge || $user?.role === 'admin'}
				sharePublic={$user?.permissions?.sharing?.public_knowledge || $user?.role === 'admin'}
				shareUsers={($user?.permissions?.access_grants?.allow_users ?? true) ||
					$user?.role === 'admin'}
			/>
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
				{$i18n.t('Create Knowledge')}
			</button>
		</div>
	</form>
</div>
