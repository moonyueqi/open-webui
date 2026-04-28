<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher } from 'svelte';
	import { onMount, getContext } from 'svelte';
	import { addUser } from '$lib/apis/auths';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import { generateInitialsImage } from '$lib/utils';
	import XMark from '$lib/components/icons/XMark.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let show = false;

	let loading = false;

	let _user = {
		name: '',
		email: '',
		password: '',
		role: 'user'
	};

	$: if (show) {
		_user = {
			name: '',
			email: '',
			password: '',
			role: 'user'
		};
	}

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

		if (!_user.password) {
			toast.error($i18n.t('Please enter your password.'));
			return;
		}

		if (!validatePassword(_user.password)) {
			toast.error($i18n.t('Password must be at least 6 characters and contain both letters and numbers.'));
			return;
		}

		loading = true;

		const res = await addUser(
			localStorage.token,
			_user.name,
			_user.email,
			_user.password,
			_user.role,
			generateInitialsImage(_user.name)
		).catch((error) => {
			toast.error(`${error}`);
		});

		if (res) {
			dispatch('save');
			show = false;
		}

		loading = false;
	};
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between items-center px-6 pt-5 pb-4">
			<div class="text-lg font-semibold text-gray-900 dark:text-gray-100">{$i18n.t('Add User')}</div>
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
				class="flex flex-col w-full space-y-3"
				on:submit|preventDefault={() => {
					submitHandler();
				}}
			>
				<div class="flex flex-col w-full">
					<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Role')}</label>
					<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
					<select
						class="w-full capitalize text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden"
						bind:value={_user.role}
						aria-label={$i18n.t('Role')}
					>
							<option value="pending"> {$i18n.t('pending')} </option>
							<option value="user"> {$i18n.t('user')} </option>
							<option value="admin"> {$i18n.t('admin')} </option>
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
							placeholder={$i18n.t('Enter Your Full Name')}
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
						/>
					</div>
				</div>

				<div class="flex flex-col w-full">
					<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Password')}</label>
					<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
						<SensitiveInput
							inputClassName="w-full text-sm text-gray-700 dark:text-gray-200 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
							type="password"
							bind:value={_user.password}
							placeholder={$i18n.t('Enter Your Password')}
							autocomplete="off"
						/>
					</div>
				</div>

				<div class="flex justify-end pt-3 mt-2 border-t border-gray-100 dark:border-gray-800">
					<button
						class="px-5 py-2 text-sm font-medium bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 transition-all rounded-lg shadow-sm flex items-center gap-2 {loading
							? ' cursor-not-allowed opacity-70'
							: ''}"
						type="submit"
						disabled={loading}
					>
						{$i18n.t('Save')}

						{#if loading}
							<Spinner />
						{/if}
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
