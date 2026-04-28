<script lang="ts">
	import { toast } from 'svelte-sonner';
	import dayjs from 'dayjs';
	import { createEventDispatcher } from 'svelte';
	import { onMount, getContext } from 'svelte';

	import { goto } from '$app/navigation';

	import { updateUserById, getUserGroupsById } from '$lib/apis/users';

	import Modal from '$lib/components/common/Modal.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import localizedFormat from 'dayjs/plugin/localizedFormat';
	import XMark from '$lib/components/icons/XMark.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import UserProfileImage from '$lib/components/chat/Settings/Account/UserProfileImage.svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();
	dayjs.extend(localizedFormat);

	export let show = false;
	export let selectedUser;
	export let sessionUser;

	$: if (show) {
		init();
	}

	const init = () => {
		if (selectedUser) {
			_user = selectedUser;
			_user.password = '';
			loadUserGroups();
		}
	};

	let _user = {
		profile_image_url: '',
		role: 'pending',
		name: '',
		email: '',
		password: ''
	};

	let userGroups: any[] | null = null;

	const validateEmail = (email: string): boolean => {
		const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$/;
		return emailRegex.test(email.trim());
	};

	const validatePassword = (password: string): boolean => {
		const hasLetter = /[a-zA-Z]/.test(password);
		const hasDigit = /\d/.test(password);
		return password.length >= 6 && hasLetter && hasDigit;
	};

	const submitHandler = async () => {
		if (!_user.name.trim()) {
			toast.error($i18n.t('Please enter your name.'));
			return;
		}

		if (!_user.email.trim()) {
			toast.error($i18n.t('Please enter your email.'));
			return;
		}

		if (!validateEmail(_user.email)) {
			toast.error($i18n.t('Please enter a valid email address.'));
			return;
		}

		if (_user.password) {
			if (!validatePassword(_user.password)) {
				toast.error($i18n.t('Password must be at least 6 characters and contain both letters and numbers.'));
				return;
			}
		}

		const res = await updateUserById(localStorage.token, selectedUser.id, _user).catch((error) => {
			toast.error(`${error}`);
		});

		if (res) {
			dispatch('save');
			show = false;
		}
	};

	const loadUserGroups = async () => {
		if (!selectedUser?.id) return;
		userGroups = null;

		userGroups = await getUserGroupsById(localStorage.token, selectedUser.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});
	};
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between items-center px-6 pt-5 pb-4">
			<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">{$i18n.t('Edit User')}</div>
			<button
				class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
				aria-label={$i18n.t('Close')}
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="px-6 pb-6 dark:text-gray-200">
			<form
				class="flex flex-col w-full"
				on:submit|preventDefault={() => {
					submitHandler();
				}}
			>
				<div class="flex items-start gap-5 mb-5 pb-5 border-b border-gray-100 dark:border-gray-800">
					<UserProfileImage
						imageClassName="size-14 md:size-18"
						bind:profileImageUrl={_user.profile_image_url}
						user={_user}
					/>

					<div class="flex-1 min-w-0 space-y-1">
						<div class="text-base font-semibold text-gray-900 dark:text-gray-100 truncate">
							{selectedUser.name}
						</div>
						<div class="text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t('Created at')} {dayjs(selectedUser.created_at * 1000).format('LL')}
						</div>
					{#if (userGroups ?? []).length > 0}
						<div class="flex flex-wrap gap-1.5 mt-2">
							{#each userGroups as userGroup}
								<Tooltip content={userGroup.name}>
									<a
										href={'/admin/users/groups?id=' + userGroup.id}
										on:click|preventDefault={() =>
											goto('/admin/users/groups?id=' + userGroup.id)}
										class="inline-flex items-center px-2 py-0.5 rounded-lg bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 text-xs font-medium hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors max-w-[10rem] truncate"
									>
										{userGroup.name}
									</a>
								</Tooltip>
							{/each}
						</div>
					{/if}
					</div>
				</div>

				<div class="space-y-3">
					<div class="flex flex-col w-full">
						<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Role')}</label>
						<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
						<select
							class="w-full text-sm capitalize text-gray-700 dark:text-gray-200 bg-transparent outline-hidden disabled:opacity-50 disabled:cursor-not-allowed"
							bind:value={_user.role}
							aria-label={$i18n.t('Role')}
							disabled={_user.id == sessionUser.id}
						>
								<option value="admin">{$i18n.t('Admin')}</option>
								<option value="user">{$i18n.t('User')}</option>
								<option value="pending">{$i18n.t('Pending')}</option>
							</select>
						</div>
					</div>

					<div class="flex flex-col w-full">
						<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Name')}</label>
						<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
						<input
							class="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
							type="text"
							bind:value={_user.name}
							aria-label={$i18n.t('Name')}
							placeholder={$i18n.t('Enter Your Name')}
							autocomplete="off"
						/>
						</div>
					</div>

					<div class="flex flex-col w-full">
						<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Email')}</label>
						<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
						<input
							class="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
							type="text"
							bind:value={_user.email}
							aria-label={$i18n.t('Email')}
							placeholder={$i18n.t('Enter Your Email')}
							autocomplete="off"
						/>
						</div>
					</div>

					{#if _user?.oauth}
						<div class="flex flex-col w-full">
							<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('OAuth ID')}</label>
							<div class="text-sm break-all space-y-1 px-3 py-2 bg-gray-50 dark:bg-gray-800/50 rounded-lg border border-gray-200/60 dark:border-gray-700/40">
								{#each Object.keys(_user.oauth) as key}
									<div class="flex items-center gap-2">
										<span class="text-gray-400 dark:text-gray-500 text-xs font-medium">{key}</span>
										<span class="text-gray-700 dark:text-gray-300">{_user.oauth[key]?.sub}</span>
									</div>
								{/each}
							</div>
						</div>
					{/if}

					<div class="flex flex-col w-full">
						<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('New Password')}</label>
						<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
							<SensitiveInput
								inputClassName="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
								type="password"
								placeholder={$i18n.t('Enter New Password')}
								bind:value={_user.password}
								autocomplete="new-password"
								required={false}
							/>
						</div>
					</div>
				</div>

				<div class="flex justify-end pt-5 mt-4 border-t border-gray-100 dark:border-gray-800">
					<button
						class="px-5 py-2 text-sm font-medium bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 transition-all rounded-lg shadow-sm flex items-center gap-2"
						type="submit"
					>
						{$i18n.t('Save')}
					</button>
				</div>
			</form>
		</div>
	</div>
</Modal>

<style>
	input::-webkit-outer-spin-button,
	input::-webkit-inner-spin-button {
		/* display: none; <- Crashes Chrome on hover */
		-webkit-appearance: none;
		margin: 0; /* <-- Apparently some margin are still there even though it's hidden */
	}

	.tabs::-webkit-scrollbar {
		display: none; /* for Chrome, Safari and Opera */
	}

	.tabs {
		-ms-overflow-style: none; /* IE and Edge */
		scrollbar-width: none; /* Firefox */
	}

	input[type='number'] {
		-moz-appearance: textfield; /* Firefox */
	}
</style>
