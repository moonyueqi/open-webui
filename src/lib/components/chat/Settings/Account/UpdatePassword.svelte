<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { updateUserPassword } from '$lib/apis/auths';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';

	const i18n = getContext('i18n');

	let show = false;
	let currentPassword = '';
	let newPassword = '';
	let newPasswordConfirm = '';

	const validatePassword = (password: string): boolean => {
		const hasLetter = /[a-zA-Z]/.test(password);
		const hasDigit = /\d/.test(password);
		return password.length >= 6 && hasLetter && hasDigit;
	};

	const updatePasswordHandler = async () => {
		if (!currentPassword) {
			toast.error($i18n.t('Please enter your current password.'));
			return;
		}

		if (!newPassword) {
			toast.error($i18n.t('Please enter your new password.'));
			return;
		}

		if (!validatePassword(newPassword)) {
			toast.error(
				$i18n.t('Password must be at least 6 characters and contain both letters and numbers.')
			);
			return;
		}

		if (newPassword === newPasswordConfirm) {
			const res = await updateUserPassword(localStorage.token, currentPassword, newPassword).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);

			if (res) {
				toast.success($i18n.t('Successfully updated.'));
			}

			currentPassword = '';
			newPassword = '';
			newPasswordConfirm = '';
		} else {
			toast.error(
				$i18n.t("The passwords you entered don't quite match. Please double-check and try again.")
			);
			newPassword = '';
			newPasswordConfirm = '';
		}
	};
</script>

<form
	class="flex flex-col text-sm"
	on:submit|preventDefault={() => {
		updatePasswordHandler();
	}}
>
	<button
		class="flex items-center justify-between w-full group"
		type="button"
		on:click={() => {
			show = !show;
		}}
	>
		<div class="flex items-center gap-2">
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4 text-gray-400 dark:text-gray-500">
				<path fill-rule="evenodd" d="M10 1a4.5 4.5 0 0 0-4.5 4.5V9H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-.5V5.5A4.5 4.5 0 0 0 10 1Zm3 8V5.5a3 3 0 1 0-6 0V9h6Z" clip-rule="evenodd" />
			</svg>
			<span class="font-medium text-gray-700 dark:text-gray-200">{$i18n.t('Change Password')}</span>
		</div>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 20 20"
			fill="currentColor"
			class="size-4 text-gray-400 transition-transform duration-200 {show ? 'rotate-180' : ''}"
		>
			<path fill-rule="evenodd" d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z" clip-rule="evenodd" />
		</svg>
	</button>

	{#if show}
		<div class="mt-4 space-y-3">
			<div class="flex flex-col w-full">
				<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Current Password')}</label>
				<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
					<SensitiveInput
						class="w-full bg-transparent text-sm text-gray-700 dark:text-gray-200 outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
						type="password"
						bind:value={currentPassword}
						placeholder={$i18n.t('Enter your current password')}
						autocomplete="current-password"
						required
					/>
				</div>
			</div>

			<div class="flex flex-col w-full">
				<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('New Password')}</label>
				<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
					<SensitiveInput
						class="w-full bg-transparent text-sm text-gray-700 dark:text-gray-200 outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
						type="password"
						bind:value={newPassword}
						placeholder={$i18n.t('Enter your new password')}
						autocomplete="new-password"
						required
					/>
				</div>
			</div>

			<div class="flex flex-col w-full">
				<label class="mb-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Confirm Password')}</label>
				<div class="px-3 py-2 rounded-lg bg-white dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/40 focus-within:border-gray-400 dark:focus-within:border-gray-500 focus-within:ring-1 focus-within:ring-gray-400/20 transition-all">
					<SensitiveInput
						class="w-full bg-transparent text-sm text-gray-700 dark:text-gray-200 outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
						type="password"
						bind:value={newPasswordConfirm}
						placeholder={$i18n.t('Confirm your new password')}
						autocomplete="off"
						required
					/>
				</div>
			</div>

			<div class="flex justify-end pt-1">
				<button
					class="px-4 py-2 text-sm font-medium bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100 transition-all rounded-lg shadow-sm"
				>
					{$i18n.t('Update password')}
				</button>
			</div>
		</div>
	{/if}
</form>
